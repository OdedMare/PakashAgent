"""Generate a schedule for a period. Every assignment carries its reason.

The model does the assigning; this module builds the slot grid it assigns
into, hands it the workplace and the constraints, and bounds what comes back.
It makes no scheduling decisions of its own
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)) —
where it drops an assignment it is because the row is unusable (a person or a
shift nobody declared), never because it disagreed with the choice.

Stateless, like `IntroInterview`: a function of the profile plus the period
it is handed. `schedule_service.py` owns persistence, which is what lets the
whole contract here be tested against a fake model with no database.

The one thing this refuses to do is store an assignment without a reason.
That is [D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required) — an
assignment nobody can account for is exactly what the reason exists to
prevent, and the failure is silent at the moment the manager would have
caught it.
"""

import datetime
import json
from typing import Any, Dict, List, Optional

from app.bl.audit import load_history
from app.bl.prompts import load
from app.common.errors import AgentError

# A period bigger than this is not a shift schedule, it is an import. Bounded
# because the slot grid is generated per day per shift and handed to the
# model in one payload.
_MAX_PERIOD_DAYS = 62
_MAX_TEXT_CHARS = 4000
# Past assignments read for the fairness tally. They are counted here and
# never sent, so this bounds the arithmetic rather than the prompt.
_MAX_HISTORY_ROWS = 400

# A period longer than this is built one chunk at a time rather than in one
# call. Seven days because a week is the unit the manager already thinks in,
# so a chunk boundary falls where a person would have put one -- and because
# the output is what actually binds: a fortnight of three daily shifts is
# ~126 assignments, each carrying its own Hebrew sentence, and a small model
# asked for all of them in one reply loses consistency somewhere in the
# middle. It is not a context limit; it is an attention one.
#
# Chunks are NOT independent. Each is told what the earlier ones decided
# (`_committed_for_model`), because a scheduler that cannot see week one will
# happily give week two to the same people -- turning a fairness feature into
# the exact unfairness it exists to prevent.
_CHUNK_DAYS = 7

# Hebrew weekdays, matching how the interview collects `days` on a shift and
# how the source files write them. Hebrew is data here, not presentation.
_HEBREW_WEEKDAYS = (
    "יום שני", "יום שלישי", "יום רביעי", "יום חמישי",
    "יום שישי", "שבת", "יום ראשון",
)

_ASSIGNMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["employee", "shift", "date", "reason"],
    "properties": {
        "employee": {"type": "string"},
        "shift": {"type": "string"},
        "date": {"type": "string"},
        # Required by the schema as well as checked below: the model is told
        # in two places because this is the field the whole decision rests on.
        "reason": {"type": "string"},
    },
}

SCHEDULE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assignments", "notes", "summary"],
    "properties": {
        "assignments": {"type": "array", "items": _ASSIGNMENT_SCHEMA},
        # What the grid does not show: a slot left short, a soft rule traded
        # against another. The manager reads these beside the schedule.
        "notes": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
}


class Scheduler:
    """Build one period's assignments from the workplace profile."""

    def __init__(self, llm):
        self._llm = llm

    def generate(
        self,
        profile: dict,
        starts_on: str,
        ends_on: str,
        availability: Optional[List[dict]] = None,
        history: Optional[List[dict]] = None,
        instructions: str = "",
    ) -> dict:
        """Slots for the period plus the model's assignments into them.

        Returns `slots`, `assignments`, `notes` and `summary`. Nothing is
        persisted here — the caller confirms and stores.
        """
        slots = build_slots(profile, starts_on, ends_on)
        if not slots:
            raise AgentError(
                "לא ניתן לבנות סידור: לא הוגדרו משמרות לתקופה הזו"
            )
        past = _bounded_rows(history, _MAX_HISTORY_ROWS)
        shifts = (profile or {}).get("shifts") or []
        employees = (profile or {}).get("employees") or []
        trimmed = _profile_for_model(profile)
        rows = _bounded_rows(availability)

        assignments: List[dict] = []
        notes: List[str] = []
        summaries: List[str] = []
        for chunk in _chunks(slots):
            # The tally is recomputed per chunk over the real history *plus*
            # what this run has already decided, so week two sees week one's
            # nights as nights. Passing the original tally to every chunk
            # would let the model hand the same person every weekend in the
            # period and never notice.
            fairness = load_history(past + assignments, shifts, employees)
            answer = self._ask({
                "profile": trimmed,
                "period": {
                    "starts_on": chunk[0]["slot_date"],
                    "ends_on": chunk[-1]["slot_date"],
                    "slots": [_slot_for_model(slot) for slot in chunk],
                },
                "availability": rows,
                # Counted rather than handed over raw. Several hundred
                # assignment rows were roughly 60% of this payload, and
                # counting them is code's job under D3 — so the model gets
                # the tally, not the rows.
                "fairness": fairness,
                "already_scheduled": _committed_for_model(assignments),
                "instructions": _bounded(instructions),
            })
            # Bounded against the whole grid, not just this chunk: a model
            # that answers with a date from next week is naming a real slot,
            # and dropping it for being outside the chunk would lose a
            # decision that is perfectly valid for the period being built.
            assignments = _merge(
                assignments,
                _assignments(answer.get("assignments"), slots, profile),
            )
            notes.extend(_lines(answer.get("notes")))
            summary = _bounded(answer.get("summary"))
            if summary:
                summaries.append(summary)

        return {
            "slots": slots,
            "assignments": assignments,
            "notes": notes,
            # One period gets one summary. Several chunks produce several, and
            # joining them is honest -- inventing a single sentence over them
            # would mean writing prose here, which is the model's job.
            "summary": _bounded(" ".join(summaries)),
        }

    def _ask(self, payload: dict) -> dict:
        answer = self._llm.complete_json(
            load("scheduler"),
            json.dumps(payload, ensure_ascii=False),
            schema=SCHEDULE_RESPONSE_SCHEMA,
        )
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר סידור לא תקין")
        return answer


def build_slots(profile: dict, starts_on: str, ends_on: str) -> List[dict]:
    """One slot per shift per day the shift actually runs.

    Built in code rather than asked of the model: which dates fall in a
    period and which weekday each one is is arithmetic, and the model has no
    business generating a calendar. It assigns people into this grid.

    A shift with no `days` runs every day — the interview is instructed to
    confirm the days, so an empty list means "not restricted" rather than
    "never", and treating it as "never" would produce an empty schedule from
    a profile that looks complete.
    """
    start = _parse_date(starts_on)
    end = _parse_date(ends_on)
    if start is None or end is None:
        raise AgentError("תאריכי התקופה אינם תקינים")
    if end < start:
        raise AgentError("תאריך הסיום מוקדם מתאריך ההתחלה")
    if (end - start).days + 1 > _MAX_PERIOD_DAYS:
        raise AgentError("התקופה ארוכה מדי לבניית סידור אחד")

    shifts = [
        shift for shift in (profile or {}).get("shifts") or []
        if isinstance(shift, dict) and _bounded(shift.get("name"))
    ]
    slots = []
    day = start
    while day <= end:
        weekday = _HEBREW_WEEKDAYS[day.weekday()]
        for shift in shifts:
            days = shift.get("days")
            runs = (
                not isinstance(days, list) or not days
                or weekday in [_bounded(item) for item in days]
            )
            if not runs:
                continue
            slots.append({
                "shift_name": _bounded(shift.get("name")),
                "slot_date": day.isoformat(),
                "weekday": weekday,
                "start_time": _bounded(shift.get("start_time")),
                "end_time": _bounded(shift.get("end_time")),
                "headcount": _headcount(shift, weekday),
                "is_on_call": bool(shift.get("is_on_call")),
            })
        day += datetime.timedelta(days=1)
    return slots


def _headcount(shift: dict, weekday: str) -> int:
    """How many people this shift needs on this weekday.

    `staffing` is per group of days because the interview asks whether the
    standard changes across the week. A group naming this weekday wins over
    the group naming none, which is the default.
    """
    staffing = shift.get("staffing")
    if not isinstance(staffing, list):
        return 1
    fallback = 1
    for group in staffing:
        if not isinstance(group, dict):
            continue
        headcount = group.get("headcount")
        if not isinstance(headcount, int) or isinstance(headcount, bool):
            continue
        days = group.get("days")
        if not isinstance(days, list) or not days:
            fallback = headcount
        elif weekday in [_bounded(item) for item in days]:
            return headcount
    return fallback


def _assignments(
    offered: Any, slots: List[dict], profile: dict
) -> List[dict]:
    """The model's assignments, bounded to what actually exists.

    Three rejections, each for a reason that is not a scheduling judgment:

    - **No reason** — D8. An assignment nobody can account for is dropped
      rather than stored, because storing it is how the decision gets quietly
      lost.
    - **A slot that is not in the grid** — the model named a shift or a date
      this period does not have, so there is nothing to assign into.
    - **A person the profile does not list** — a name nobody declared cannot
      be rostered onto a real shift.

    Everything else is kept exactly as the model decided it, including
    choices the audit will go on to warn about: warning is the audit's job,
    and refusing them here would make this code the authority D3 says it is
    not.
    """
    if not isinstance(offered, list):
        return []
    known_slots = {
        (slot["shift_name"], slot["slot_date"]): slot for slot in slots
    }
    known_people = {
        _bounded(person.get("name"))
        for person in (profile or {}).get("employees") or []
        if isinstance(person, dict)
    }
    known_people.discard("")

    assignments, seen = [], set()
    for item in offered:
        if not isinstance(item, dict):
            continue
        employee = _bounded(item.get("employee"))
        shift = _bounded(item.get("shift"))
        date = _bounded(item.get("date"))
        reason = _bounded(item.get("reason"))
        if not employee or not shift or not date or not reason:
            continue
        if (shift, date) not in known_slots:
            continue
        if known_people and employee not in known_people:
            continue
        key = (employee, shift, date)
        if key in seen:
            continue
        seen.add(key)
        assignments.append({
            "employee": employee, "shift": shift,
            "date": date, "reason": reason,
        })
    return assignments


def _profile_for_model(profile: dict) -> dict:
    """The profile, trimmed to what scheduling needs.

    Rules travel as the manager's own sentences
    ([D2](../../../docs/DECISIONS.md#d2--rules-stay-natural-language)) — not
    parsed, not normalized, not turned into typed records.
    """
    profile = profile if isinstance(profile, dict) else {}
    return {
        "workplace": profile.get("workplace") or {},
        "employees": profile.get("employees") or [],
        "shifts": profile.get("shifts") or [],
        "rules": profile.get("rules") or [],
        "dependencies": profile.get("dependencies") or [],
        "training_policy": profile.get("training_policy") or {},
        "rest_policy": profile.get("rest_policy") or "",
        "weekend_policy": profile.get("weekend_policy") or "",
        "fairness_policy": profile.get("fairness_policy") or "",
        "conflict_policy": profile.get("conflict_policy") or "",
    }


def _slot_for_model(slot: dict) -> dict:
    return {
        "shift": slot["shift_name"],
        "date": slot["slot_date"],
        "weekday": slot["weekday"],
        "start_time": slot["start_time"],
        "end_time": slot["end_time"],
        "headcount": slot["headcount"],
        "is_on_call": slot["is_on_call"],
    }


def _bounded_rows(rows: Any, limit: int = 200) -> List[dict]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)][-limit:]


def _lines(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [line for line in (_bounded(item) for item in value) if line]


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _parse_date(value: Any) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(_bounded(value))
    except (ValueError, TypeError):
        return None


__all__ = ["Scheduler", "SCHEDULE_RESPONSE_SCHEMA", "build_slots"]
