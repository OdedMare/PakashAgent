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
import logging
import time
from typing import Any, Dict, List, Optional

from app.bl.audit import (
    CONSECUTIVE,
    DOUBLE_BOOKED,
    OVER_HOURS,
    OVERSTAFFED,
    SHORT_REST,
    UNAVAILABLE,
    UNFILLED,
    audit,
    constraint_conflicts,
    load_history,
)
from app.bl.prompts import load
from app.common.errors import AgentError

# A period bigger than this is not a shift schedule, it is an import. Bounded
# because the slot grid is generated per day per shift and handed to the
# model in one payload.
# Checkpointed daily generation makes long planning horizons safe to resume.
# One leap year is a useful product ceiling; beyond that belongs in a separate
# forecast rather than one living operational schedule.
_MAX_PERIOD_DAYS = 366
_MAX_TEXT_CHARS = 4000
# Past assignments read for the fairness tally. They are counted here and
# never sent, so this bounds the arithmetic rather than the prompt.
_MAX_HISTORY_ROWS = 400

_log = logging.getLogger("pakash.scheduler")

# Problems code can prove from the accumulated roster. The model gets one
# focused chance to repair the current day; a second bad answer stays visible
# as an audit warning instead of entering an unbounded model loop.
_REPAIRABLE_WARNING_CODES = frozenset({
    CONSECUTIVE,
    DOUBLE_BOOKED,
    OVER_HOURS,
    OVERSTAFFED,
    SHORT_REST,
    UNAVAILABLE,
    UNFILLED,
})

# A period is built in bounded chunks. Seven days is the calendar ceiling,
# while staffing volume is the output ceiling: a busy week can require far
# more JSON rows than a quiet fortnight, and small models otherwise tend to
# answer only the first day while still returning valid JSON.
#
# Chunks are NOT independent. Each is told what the earlier ones decided
# (`_committed_for_model`), because a scheduler that cannot see week one will
# happily give week two to the same people -- turning a fairness feature into
# the exact unfairness it exists to prevent.
_CHUNK_DAYS = 7
_MAX_ASSIGNMENTS_PER_CHUNK = 14

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
        required_assignments: Optional[List[dict]] = None,
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

        required = _required_assignments(required_assignments, slots, profile)
        assignments: List[dict] = list(required)
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
                "required_assignments": _committed_for_model(required),
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

    def generate_day(
        self,
        profile: dict,
        day: str,
        availability: Optional[List[dict]] = None,
        history: Optional[List[dict]] = None,
        instructions: str = "",
        required_assignments: Optional[List[dict]] = None,
        already_scheduled: Optional[List[dict]] = None,
    ) -> dict:
        """Generate and verify exactly one date.

        Long ranges call this once per date, in order. Earlier dates are
        supplied through ``already_scheduled`` so rest and cumulative load do
        not reset at midnight. One repair call is allowed when deterministic
        checks find a contradiction or the model returned unusable rows.
        """
        started = time.monotonic()
        slots = build_slots(profile, day, day)
        if not slots:
            return {
                "slots": [], "assignments": [], "notes": [], "summary": "",
                "metrics": _metrics(day, started, status="skipped"),
            }

        profile = profile if isinstance(profile, dict) else {}
        shifts = profile.get("shifts") or []
        employees = profile.get("employees") or []
        availability = _availability_for_day(availability, day)
        committed = _bounded_rows(already_scheduled)
        required = _required_assignments(
            required_assignments, slots, profile
        )
        candidates = _candidates(profile, slots, availability)
        payload = {
            "profile": _profile_for_model(profile),
            "period": {
                "starts_on": day,
                "ends_on": day,
                "slots": [
                    _slot_for_model(slot, index, candidates)
                    for index, slot in enumerate(slots, 1)
                ],
            },
            "candidate_employees": candidates["employees"],
            "availability": availability,
            "fairness": load_history(
                _bounded_rows(history, _MAX_HISTORY_ROWS)
                + [row for row in committed if _bounded(row.get("date")) < day]
                + required,
                shifts,
                employees,
            ),
            # Only yesterday is needed verbatim for cross-midnight rest. Load
            # totals above carry the rest of the range without making this
            # list grow on every day of a long schedule.
            "already_scheduled": _merge(
                _previous_day(committed, day),
                _committed_for_model(required),
            ),
            "required_assignments": _committed_for_model(required),
            "instructions": _bounded(instructions),
        }
        answer = self._ask(payload, schema=_day_schema(slots, candidates))
        usage = _usage(answer)
        accepted, rejected = _read_day_assignments(
            answer.get("assignments"), slots, profile, candidates
        )
        current = _replace_day(committed, required + accepted, day)
        warnings = _day_warnings(
            current, slots, profile, availability, candidates, day
        )
        repaired = False

        if rejected or warnings:
            repair_payload = dict(payload)
            repair_payload["repair"] = {
                "rejected_rows": rejected,
                "warnings": [item["message"] for item in warnings],
                "instruction": (
                    "החזר מחדש את כל השיבוצים ליום הזה בלבד. "
                    "תקן את הבעיות המפורטות ואל תשנה ימים קודמים."
                ),
            }
            repaired_answer = self._ask(
                repair_payload, schema=_day_schema(slots, candidates)
            )
            usage = {
                key: usage.get(key, 0) + _usage(repaired_answer).get(key, 0)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
            repaired_rows, repair_rejected = _read_day_assignments(
                repaired_answer.get("assignments"), slots, profile, candidates
            )
            current = _replace_day(committed, required + repaired_rows, day)
            rejected.extend(repair_rejected)
            answer = repaired_answer
            repaired = True

        final_rows = [row for row in current if row.get("date") == day]
        final_warnings = _audit_for_day(
            current, slots, profile, availability, day
        )
        notes = _lines(answer.get("notes"))
        if rejected:
            notes.append(
                "%d שיבוצים לא תקינים שהחזיר המודל לא נשמרו." % len(rejected)
            )
        metrics = _metrics(
            day,
            started,
            status="complete",
            returned=len(answer.get("assignments") or []),
            accepted=len(final_rows),
            rejected=len(rejected),
            warnings=len(final_warnings),
            repaired=repaired,
            usage=usage,
        )
        _log.info(
            "schedule day=%s status=%s assignments=%d rejected=%d "
            "warnings=%d repaired=%s tokens=%d duration_ms=%d",
            day, metrics["status"], metrics["accepted"], metrics["rejected"],
            metrics["warnings"], metrics["repaired"], metrics["total_tokens"],
            metrics["duration_ms"],
        )
        return {
            "slots": slots,
            "assignments": final_rows,
            "notes": notes,
            "summary": _bounded(answer.get("summary")),
            "warnings": final_warnings,
            "metrics": metrics,
        }

    def _ask(self, payload: dict, schema: Optional[dict] = None) -> dict:
        answer = self._llm.complete_json(
            load("scheduler"),
            json.dumps(payload, ensure_ascii=False),
            schema=schema or SCHEDULE_RESPONSE_SCHEMA,
            flow="scheduler",
        )
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר סידור לא תקין")
        return answer


def _chunks(slots: List[dict]) -> List[List[dict]]:
    """Split the grid without dividing a day or overloading one model call.

    Split on dates rather than on slot count, so a day is never divided across
    two calls: half a Tuesday in one request and half in another is how the
    same person ends up on two shifts at once, and neither call would have the
    information to notice.

    Staffing headcount, not slot count, estimates the rows the model must
    return. A quiet week remains one call; a busy week is split even when it
    spans only seven days.
    """
    dates = sorted({slot["slot_date"] for slot in slots})
    by_date: Dict[str, List[dict]] = {}
    for slot in slots:
        by_date.setdefault(slot["slot_date"], []).append(slot)

    chunks: List[List[dict]] = []
    chunk: List[dict] = []
    demand = 0
    days = 0
    for date in dates:
        day_slots = by_date[date]
        day_demand = sum(max(1, slot.get("headcount", 1)) for slot in day_slots)
        if chunk and (
            days >= _CHUNK_DAYS
            or demand + day_demand > _MAX_ASSIGNMENTS_PER_CHUNK
        ):
            chunks.append(chunk)
            chunk = []
            demand = 0
            days = 0
        chunk.extend(day_slots)
        demand += day_demand
        days += 1
    if chunk:
        chunks.append(chunk)
    return chunks


def _merge(existing: List[dict], incoming: List[dict]) -> List[dict]:
    """Assignments from a later chunk added to what earlier ones decided.

    A duplicate is kept as the earlier chunk placed it. The later call is the
    one working from incomplete information -- it was told what was already
    scheduled and answered with it anyway -- so the first decision stands and
    nothing silently overwrites a slot the manager may already be looking at.
    """
    seen = {
        (row["employee"], row["shift"], row["date"]) for row in existing
    }
    merged = list(existing)
    for row in incoming:
        key = (row["employee"], row["shift"], row["date"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def _committed_for_model(assignments: List[dict]) -> List[dict]:
    """What earlier chunks already placed, as this chunk needs to see it.

    Without the reasons: the next chunk needs to know a slot is taken and who
    is on it, not to re-read a paragraph of justification per row. Dropping
    them is most of the size of this list, and it is the field the chunk has
    no use for.
    """
    return [
        {
            "employee": row["employee"],
            "shift": row["shift"],
            "date": row["date"],
        }
        for row in assignments
    ]


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
                or _weekday_key(weekday) in {
                    _weekday_key(item) for item in days
                }
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
        elif _weekday_key(weekday) in {_weekday_key(item) for item in days}:
            return headcount
    return fallback


def _weekday_key(value: Any) -> str:
    """The weekday independent of the optional Hebrew ``יום`` prefix.

    Interview answers naturally contain both ``ראשון`` and ``יום ראשון``.
    They name the same day, and treating them as different silently removed
    every prefixed weekday except שבת from generated schedules.
    """
    value = _bounded(value)
    return value[4:].strip() if value.startswith("יום ") else value


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


def _required_assignments(
    offered: Any, slots: List[dict], profile: dict
) -> List[dict]:
    """Validate and pin the placements explicitly chosen by the manager."""
    if not offered:
        return []
    known_slots = {
        (slot["shift_name"], slot["slot_date"]) for slot in slots
    }
    known_people = {
        _bounded(person.get("name"))
        for person in (profile or {}).get("employees") or []
        if isinstance(person, dict)
    }
    required, seen = [], set()
    for item in offered:
        employee = _bounded(item.get("employee")) if isinstance(item, dict) else ""
        shift = _bounded(item.get("shift")) if isinstance(item, dict) else ""
        date = _bounded(item.get("date")) if isinstance(item, dict) else ""
        if employee not in known_people:
            raise AgentError("העובד שנבחר לשיבוץ החובה אינו קיים בצוות")
        if (shift, date) not in known_slots:
            raise AgentError("המשמרת שנבחרה לשיבוץ החובה אינה קיימת בשבוע הזה")
        key = (employee, shift, date)
        if key in seen:
            continue
        seen.add(key)
        required.append({
            "employee": employee,
            "shift": shift,
            "date": date,
            "reason": "שיבוץ חובה שנבחר על ידי המנהל בעת בניית הסידור",
        })
    return required


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


def _slot_for_model(
    slot: dict,
    index: Optional[int] = None,
    candidates: Optional[dict] = None,
) -> dict:
    shaped = {
        "shift": slot["shift_name"],
        "date": slot["slot_date"],
        "weekday": slot["weekday"],
        "start_time": slot["start_time"],
        "end_time": slot["end_time"],
        "headcount": slot["headcount"],
        "is_on_call": slot["is_on_call"],
    }
    if index is not None:
        slot_id = "slot-%d" % index
        shaped["id"] = slot_id
        shaped["candidate_employee_ids"] = (
            candidates or {}
        ).get("by_slot", {}).get(slot_id, [])
    return shaped


def _availability_for_day(rows: Any, day: str) -> List[dict]:
    """Only constraints that can affect this model call."""
    shaped = []
    for row in _bounded_rows(rows):
        date = _bounded(row.get("date") or row.get("constraint_date"))
        if date != day:
            continue
        shaped.append({
            "employee": _bounded(row.get("employee")),
            "date": date,
            "shift": _bounded(row.get("shift") or row.get("shift_name")),
            "available": bool(row.get("available")),
            "start_time": _bounded(row.get("start_time")),
            "end_time": _bounded(row.get("end_time")),
            "is_hard": row.get("is_hard", True) is not False,
            "reason": _bounded(row.get("reason")),
        })
    return shaped


def _candidates(profile: dict, slots: List[dict], availability: List[dict]) -> dict:
    """Legal employee choices per slot, with small stable prompt-local ids."""
    employees = []
    id_by_name = {}
    for index, person in enumerate((profile or {}).get("employees") or [], 1):
        if not isinstance(person, dict):
            continue
        name = _bounded(person.get("name"))
        if not name:
            continue
        employee_id = "employee-%d" % index
        id_by_name[name] = employee_id
        employees.append({
            "id": employee_id,
            "name": name,
            "roles": person.get("roles") or [],
            "eligible_shifts": person.get("eligible_shifts") or [],
            "max_weekly_hours": person.get("max_weekly_hours") or 0,
            "is_trainee": bool(person.get("is_trainee")),
        })

    by_slot = {}
    for index, slot in enumerate(slots, 1):
        slot_id = "slot-%d" % index
        eligible = []
        for person in (profile or {}).get("employees") or []:
            if not isinstance(person, dict):
                continue
            name = _bounded(person.get("name"))
            allowed = person.get("eligible_shifts")
            if isinstance(allowed, list) and allowed and slot["shift_name"] not in allowed:
                continue
            assignment = {
                "employee": name,
                "date": slot["slot_date"],
                "shift": slot["shift_name"],
                "start_time": slot.get("start_time"),
                "end_time": slot.get("end_time"),
            }
            if any(
                item.get("is_hard", True) is not False
                and constraint_conflicts(assignment, item)
                for item in availability if isinstance(item, dict)
            ):
                continue
            if name in id_by_name:
                eligible.append(id_by_name[name])
        by_slot[slot_id] = eligible
    return {
        "employees": employees,
        "id_by_name": id_by_name,
        "name_by_id": {value: key for key, value in id_by_name.items()},
        "by_slot": by_slot,
    }


def _day_schema(slots: List[dict], candidates: dict) -> dict:
    """A response schema whose ids can only name today's actual choices."""
    slot_ids = ["slot-%d" % index for index in range(1, len(slots) + 1)]
    employee_ids = [item["id"] for item in candidates["employees"]]
    assignment = {
        "type": "object",
        "additionalProperties": False,
        "required": ["employee_id", "slot_id", "reason"],
        "properties": {
            "employee_id": (
                {"type": "string", "enum": employee_ids}
                if employee_ids else {"type": "string"}
            ),
            "slot_id": {"type": "string", "enum": slot_ids},
            "reason": {"type": "string", "minLength": 4},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["assignments", "notes", "summary"],
        "properties": {
            "assignments": {
                "type": "array",
                "maxItems": sum(
                    max(1, int(slot.get("headcount", 1))) for slot in slots
                ),
                "items": assignment,
            },
            "notes": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
    }


def _read_day_assignments(
    offered: Any, slots: List[dict], profile: dict, candidates: dict
) -> tuple:
    """Translate prompt-local ids and retain an auditable rejection count."""
    if not isinstance(offered, list):
        return [], [{"reason": "assignments is not a list"}]
    slot_by_id = {
        "slot-%d" % index: slot for index, slot in enumerate(slots, 1)
    }
    translated = []
    rejected = []
    for item in offered:
        if not isinstance(item, dict):
            rejected.append({"reason": "row is not an object"})
            continue
        employee_id = _bounded(item.get("employee_id"))
        slot_id = _bounded(item.get("slot_id"))
        if employee_id or slot_id:
            slot = slot_by_id.get(slot_id)
            employee = candidates["name_by_id"].get(employee_id, "")
            if (
                slot is None
                or employee_id not in candidates["by_slot"].get(slot_id, [])
            ):
                rejected.append({
                    "employee_id": employee_id,
                    "slot_id": slot_id,
                    "reason": "unknown or ineligible candidate",
                })
                continue
            translated.append({
                "employee": employee,
                "shift": slot["shift_name"],
                "date": slot["slot_date"],
                "reason": item.get("reason"),
            })
        else:
            # Backward-compatible with older compatible servers and scripted
            # tests while the prompt contract rolls forward to ids.
            translated.append(item)
    accepted = _assignments(translated, slots, profile)
    if len(accepted) < len(translated):
        rejected.extend(
            {"reason": "missing reason, duplicate, or unknown slot/person"}
            for _ in range(len(translated) - len(accepted))
        )
    return accepted, rejected


def _replace_day(existing: List[dict], incoming: List[dict], day: str) -> List[dict]:
    return _merge(
        [row for row in existing if row.get("date") != day], incoming
    )


def _previous_day(assignments: List[dict], day: str) -> List[dict]:
    parsed = _parse_date(day)
    if parsed is None:
        return []
    yesterday = (parsed - datetime.timedelta(days=1)).isoformat()
    return _committed_for_model([
        row for row in assignments if row.get("date") == yesterday
    ])


def _audit_for_day(
    assignments: List[dict], slots: List[dict], profile: dict,
    availability: List[dict], day: str,
) -> List[dict]:
    warnings = audit(
        assignments,
        (profile or {}).get("shifts") or [],
        (profile or {}).get("employees") or [],
        availability=availability,
        profile=profile,
        slots=slots,
    )
    return [
        item for item in warnings
        if item.get("date") in ("", day, None)
    ]


def _day_warnings(
    assignments: List[dict], slots: List[dict], profile: dict,
    availability: List[dict], candidates: dict, day: str,
) -> List[dict]:
    warnings = [
        item for item in _audit_for_day(
            assignments, slots, profile, availability, day
        )
        if item.get("code") in _REPAIRABLE_WARNING_CODES
        and item.get("severity") == "warning"
    ]
    # Do not spend a repair call asking for impossible coverage. If a slot has
    # fewer legal candidates than seats, the honest outcome is an unfilled
    # warning for the manager.
    fillable = {
        slot["shift_name"]: len(candidates["by_slot"].get("slot-%d" % index, []))
        >= max(1, int(slot.get("headcount", 1)))
        for index, slot in enumerate(slots, 1)
    }
    return [
        item for item in warnings
        if item.get("code") != UNFILLED or fillable.get(item.get("shift"), False)
    ]


def _metrics(
    day: str, started: float, status: str, returned: int = 0,
    accepted: int = 0, rejected: int = 0, warnings: int = 0,
    repaired: bool = False, usage: Optional[dict] = None,
) -> dict:
    return {
        "date": day,
        "status": status,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "returned": returned,
        "accepted": accepted,
        "rejected": rejected,
        "warnings": warnings,
        "repaired": repaired,
        "prompt_tokens": int((usage or {}).get("prompt_tokens") or 0),
        "completion_tokens": int((usage or {}).get("completion_tokens") or 0),
        "total_tokens": int((usage or {}).get("total_tokens") or 0),
    }


def _usage(answer: Any) -> dict:
    usage = answer.get("_usage") if isinstance(answer, dict) else None
    return usage if isinstance(usage, dict) else {}


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
