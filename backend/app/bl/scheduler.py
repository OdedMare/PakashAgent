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
    MISSING_ROLE,
    OVER_HOURS,
    OVERSTAFFED,
    SHORT_REST,
    UNAVAILABLE,
    UNFILLED,
    audit,
    constraint_conflicts,
    counts_toward_staffing,
    load_history,
)
from app.bl import rotation as rotation_cycle
from app.bl.prompts import load
from app.common.config.settings import (
    GENERATION_MODES, MODE_DAY, MODE_WEEK,
)
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
    MISSING_ROLE,
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

# How a period is divided into model calls, re-exported from the layer that
# owns the vocabulary. `MODE_DAY` asks for one date at a time -- the most
# verifiable unit, because every row is checked against that date's own
# candidate lists and repaired in isolation. `MODE_WEEK` asks for up to a week
# in one call, which costs the scheduler prompt once instead of seven times,
# at the price of a coarser repair: one bad row sends the whole span back.
#
# Both run the identical pipeline (`generate_span`); the mode chooses only how
# wide each call is. That is why this is a setting rather than two code paths.

# The staffing demand one span may carry in week mode. Far above
# `_MAX_ASSIGNMENTS_PER_CHUNK` because the daily path's response schema pins
# every row to an enumerated slot and an enumerated candidate, so the model is
# not free to invent rows the way the legacy free-text path was -- the ceiling
# is about how much one answer can hold, not about how much can be trusted.
# A week that needs more than this is split, which is why week mode is a
# ceiling rather than a promise of exactly seven days.
_MAX_ASSIGNMENTS_PER_SPAN = 70

# Hebrew weekdays, matching how the interview collects `days` on a shift and
# how the source files write them. Hebrew is data here, not presentation.
_HEBREW_WEEKDAYS = (
    "יום שני", "יום שלישי", "יום רביעי", "יום חמישי",
    "יום שישי", "שבת", "יום ראשון",
)

# Availability rows this module derived from the rotation itself rather than
# read from the manager's constraints. They are the cycle expressed as
# unavailability, so an assignment contradicting one is not a judgment call
# the audit should merely remark on: it puts somebody in on a weekend that
# is not theirs, which is the drift `rotation.py` exists to prevent. Both
# sources are refused on every generation path, the legacy chunked one
# included -- the daily path's candidate lists already exclude them, and a
# gate in only one of the two is a gate the other route walks around.
_ROTATION_SOURCES = frozenset({"rotation", "closure"})

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
        preferences: Optional[List[dict]] = None,
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
        rows = effective_availability(
            profile, availability, starts_on, ends_on
        )

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
                "preferences": _preferences_for_model(preferences),
                "period": {
                    "starts_on": chunk[0]["slot_date"],
                    "ends_on": chunk[-1]["slot_date"],
                    "slots": [_slot_for_model(slot) for slot in chunk],
                },
                "availability": _availability_for_dates(
                    rows, {slot["slot_date"] for slot in chunk}
                ),
                "closures": _closures_for_model(
                    profile, chunk[0]["slot_date"], chunk[-1]["slot_date"]
                ),
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
                _assignments(
                    answer.get("assignments"), slots, profile, rows
                ),
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
        preferences: Optional[List[dict]] = None,
    ) -> dict:
        """Generate and verify exactly one date.

        The one-date case of `generate_span`, kept as its own name because it
        is what every caller outside the range job asks for and reads better
        than a span whose ends are equal.
        """
        return self.generate_span(
            profile, day, day,
            availability=availability,
            history=history,
            instructions=instructions,
            required_assignments=required_assignments,
            already_scheduled=already_scheduled,
            preferences=preferences,
        )

    def generate_span(
        self,
        profile: dict,
        starts_on: str,
        ends_on: str,
        availability: Optional[List[dict]] = None,
        history: Optional[List[dict]] = None,
        instructions: str = "",
        required_assignments: Optional[List[dict]] = None,
        already_scheduled: Optional[List[dict]] = None,
        preferences: Optional[List[dict]] = None,
    ) -> dict:
        """Generate and verify one contiguous stretch of dates.

        A range job calls this once per span, in order — one date at a time in
        `MODE_DAY`, up to a week in `MODE_WEEK`. Earlier spans are supplied
        through ``already_scheduled`` so rest and cumulative load do not reset
        at a span boundary. One repair call is allowed when deterministic
        checks find a contradiction or the model returned unusable rows.

        Widening the span does not weaken any check: the candidate lists, the
        response schema, the rejection rules and the audit are all built over
        whatever dates this call covers, so a week is verified exactly as
        seven separate days are. What it changes is the *granularity of the
        repair* — one bad row sends the whole span back rather than one date —
        and the price of a failure, which is why the mode is the manager's
        choice rather than this module's.
        """
        started = time.monotonic()
        slots = build_slots(profile, starts_on, ends_on)
        if not slots:
            return {
                "slots": [], "assignments": [], "notes": [], "summary": "",
                "metrics": _metrics(
                    starts_on, started, status="skipped", through=ends_on
                ),
            }

        profile = profile if isinstance(profile, dict) else {}
        shifts = profile.get("shifts") or []
        employees = profile.get("employees") or []
        dates = {slot["slot_date"] for slot in slots}
        availability = effective_availability(
            profile, availability, starts_on, ends_on
        )
        committed = _bounded_rows(already_scheduled)
        required = _required_assignments(
            required_assignments, slots, profile
        )
        candidates = _candidates(profile, slots, availability)
        payload = {
            # Without `employees`: `candidate_employees` below is the same
            # roster, filtered and keyed by the ids the schema accepts, and
            # sending both put the whole staff list in the request twice.
            "profile": _profile_beside_candidates(profile),
            "preferences": _preferences_for_model(preferences),
            "period": {
                "starts_on": starts_on,
                "ends_on": ends_on,
                "slots": [
                    _slot_for_model(slot, index, candidates)
                    for index, slot in enumerate(slots, 1)
                ],
            },
            "candidate_employees": candidates["employees"],
            "availability": availability,
            # The closure cycle, already worked out. Handed over as a fact so
            # the model reads whose weekend it is rather than deriving a
            # phase it has no way to check.
            "closures": _closures_for_model(profile, starts_on, ends_on),
            "fairness": load_history(
                _bounded_rows(history, _MAX_HISTORY_ROWS)
                + [
                    row for row in committed
                    if _bounded(row.get("date")) < starts_on
                ]
                + required,
                shifts,
                employees,
            ),
            # Only the day before the span is needed verbatim, for
            # cross-midnight rest. Load totals above carry the rest of the
            # range without making this list grow on every day of a long
            # schedule.
            "already_scheduled": _merge(
                _previous_day(committed, starts_on),
                _committed_for_model(required),
            ),
            "required_assignments": _committed_for_model(required),
            "instructions": _bounded(instructions),
        }
        answer = self._ask(payload, schema=_day_schema(slots, candidates))
        usage = _usage(answer)
        accepted, rejected = _read_day_assignments(
            answer.get("assignments"), slots, profile, candidates,
            availability,
        )
        current = _replace_span(committed, required + accepted, dates)
        warnings = _span_warnings(
            current, slots, profile, availability, candidates, dates
        )
        repaired = False

        if rejected or warnings:
            repair_payload = dict(payload)
            repair_payload["repair"] = {
                "rejected_rows": rejected,
                "warnings": [item["message"] for item in warnings],
                "instruction": (
                    "החזר מחדש את כל השיבוצים לתאריכים האלה בלבד. "
                    "תקן את הבעיות המפורטות ואל תשנה תאריכים קודמים."
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
                repaired_answer.get("assignments"), slots, profile,
                candidates, availability,
            )
            repaired_current = _replace_span(
                committed, required + repaired_rows, dates
            )
            repaired_warnings = _span_warnings(
                repaired_current, slots, profile, availability, candidates,
                dates,
            )
            # A repair is another model answer, not proof of improvement.
            # Keep the first answer when the second introduces more concrete
            # rejected rows or audit warnings.
            if len(repair_rejected) + len(repaired_warnings) <= (
                len(rejected) + len(warnings)
            ):
                current = repaired_current
                answer = repaired_answer
            rejected.extend(repair_rejected)
            repaired = True

        final_rows = [row for row in current if row.get("date") in dates]
        final_warnings = _audit_for_span(
            current, slots, profile, availability, dates
        )
        notes = _lines(answer.get("notes"))
        if rejected:
            notes.append(
                "%d שיבוצים לא תקינים שהחזיר המודל לא נשמרו." % len(rejected)
            )
        metrics = _metrics(
            starts_on,
            started,
            status="complete",
            through=ends_on,
            returned=len(answer.get("assignments") or []),
            accepted=len(final_rows),
            rejected=len(rejected),
            warnings=len(final_warnings),
            repaired=repaired,
            usage=usage,
        )
        _log.info(
            "schedule span=%s..%s status=%s assignments=%d rejected=%d "
            "warnings=%d repaired=%s tokens=%d duration_ms=%d",
            starts_on, ends_on, metrics["status"], metrics["accepted"],
            metrics["rejected"], metrics["warnings"], metrics["repaired"],
            metrics["total_tokens"], metrics["duration_ms"],
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


def plan_spans(
    profile: dict, starts_on: str, ends_on: str, mode: str = MODE_DAY
) -> List[dict]:
    """The date ranges a range job will ask the model for, one call each.

    Returned as `{"date", "through", "dates"}` rather than a pair, because
    the caller counts progress in *dates* however wide a call is: a manager
    watching "4 of 14 days" must not see the bar jump by seven because the
    unit of work changed underneath them.

    In `MODE_DAY` every span is one date. In `MODE_WEEK` the same `_chunks`
    that bounds the legacy path bounds this one, so a week is a ceiling and
    not a promise: a span never crosses seven days, and a week whose staffing
    demand would not fit one answer is split rather than truncated.
    """
    slots = build_slots(profile, starts_on, ends_on)
    if mode != MODE_WEEK:
        return [
            {"date": date, "through": date, "dates": [date]}
            for date in sorted({slot["slot_date"] for slot in slots})
        ]
    spans = []
    for chunk in _chunks(slots, _MAX_ASSIGNMENTS_PER_SPAN):
        dates = sorted({slot["slot_date"] for slot in chunk})
        spans.append({
            "date": dates[0], "through": dates[-1], "dates": dates,
        })
    return spans


def _chunks(
    slots: List[dict], demand_limit: int = _MAX_ASSIGNMENTS_PER_CHUNK
) -> List[List[dict]]:
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
            or demand + day_demand > demand_limit
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
            headcount, required_roles = _staffing_requirements(shift, weekday)
            slots.append({
                "shift_name": _bounded(shift.get("name")),
                "slot_date": day.isoformat(),
                "weekday": weekday,
                "start_time": _bounded(shift.get("start_time")),
                "end_time": _bounded(shift.get("end_time")),
                "headcount": headcount,
                "required_roles": required_roles,
                "requires_shift_manager": bool(
                    shift.get("requires_shift_manager")
                ),
                "is_on_call": bool(shift.get("is_on_call")),
            })
        day += datetime.timedelta(days=1)
    return slots


def _staffing_requirements(shift: dict, weekday: str) -> tuple:
    """How many people and which roles this shift needs on this weekday.

    `staffing` is per group of days because the interview asks whether the
    standard changes across the week. A group naming this weekday wins over
    the group naming none, which is the default.
    """
    staffing = shift.get("staffing")
    if not isinstance(staffing, list):
        return 1, []
    fallback = (1, [])
    for group in staffing:
        if not isinstance(group, dict):
            continue
        headcount = group.get("headcount")
        if not isinstance(headcount, int) or isinstance(headcount, bool):
            continue
        days = group.get("days")
        if not isinstance(days, list) or not days:
            fallback = (headcount, _role_list(group.get("required_roles")))
        elif _weekday_key(weekday) in {_weekday_key(item) for item in days}:
            return headcount, _role_list(group.get("required_roles"))
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
    offered: Any, slots: List[dict], profile: dict,
    availability: Optional[List[dict]] = None,
) -> List[dict]:
    """The model's assignments, bounded to what actually exists.

    Four rejections, each for a reason that is not a scheduling judgment:

    - **No reason** — D8. An assignment nobody can account for is dropped
      rather than stored, because storing it is how the decision gets quietly
      lost.
    - **A slot that is not in the grid** — the model named a shift or a date
      this period does not have, so there is nothing to assign into.
    - **A person the profile does not list** — a name nobody declared cannot
      be rostered onto a real shift.
    - **A day the rotation says is not theirs** — the closure cycle is
      arithmetic this module already did (`_rotation_availability` and
      `_closure_availability`), and a row contradicting it puts somebody in
      on a weekend belonging to another group. That is not the model
      weighing a soft rule differently; it is the cycle the unit planned its
      month around being silently re-phased, so the row is dropped here as
      well as excluded from the candidate lists.

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
        slot = known_slots[(shift, date)]
        assignment = {
            "employee": employee, "shift": shift, "date": date,
            "start_time": slot.get("start_time"),
            "end_time": slot.get("end_time"),
        }
        if any(
            row.get("source") in _ROTATION_SOURCES
            and constraint_conflicts(assignment, row)
            for row in (availability or []) if isinstance(row, dict)
        ):
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
    """The complete canonical interview profile used for scheduling.

    The interview schema is already the boundary. A second field list here
    made newly collected facts disappear until both contracts were updated.
    """
    return profile if isinstance(profile, dict) else {}


def _profile_beside_candidates(profile: dict) -> dict:
    """The profile as the span path sends it: everything except the roster.

    `candidate_employees` already carries every employee, in the same call,
    filtered to those legally available for these slots and keyed by the ids
    the response schema will accept. Sending `employees` as well repeats the
    entire roster verbatim — on a thirty-person team that measured at roughly
    a third of the request — and the duplicate is the copy the model must
    *not* choose from, since a name outside the candidate lists is rejected
    on the way back anyway.

    A blacklist of exactly one key rather than a field list, for the reason
    `_profile_for_model` gives above: a whitelist here is how newly collected
    interview facts disappear until two contracts are updated. Everything the
    interview ever learns still travels, minus the one list sent twice.
    """
    if not isinstance(profile, dict):
        return {}
    return {
        key: value for key, value in profile.items() if key != "employees"
    }


def _preferences_for_model(preferences: Any) -> List[dict]:
    """Confirmed standing preferences, kept distinct from hard rules."""
    shaped = []
    for row in preferences or []:
        if not isinstance(row, dict):
            continue
        shaped.append({
            "kind": _bounded(row.get("kind")),
            "subject": _bounded(row.get("subject")),
            "text": _bounded(row.get("text")),
        })
    return shaped[:40]


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
        "required_roles": _role_list(slot.get("required_roles")),
        "requires_shift_manager": bool(slot.get("requires_shift_manager")),
        "is_on_call": slot["is_on_call"],
    }
    if index is not None:
        slot_id = "slot-%d" % index
        shaped["id"] = slot_id
        shaped["candidate_employee_ids"] = (
            candidates or {}
        ).get("by_slot", {}).get(slot_id, [])
    return shaped


def _availability_for_dates(rows: Any, dates: set) -> List[dict]:
    return [
        row for row in _bounded_rows(rows, 2000)
        if _date_text(row.get("date") or row.get("constraint_date")) in dates
    ]


def effective_availability(
    profile: dict, rows: Any, starts_on: str, ends_on: str
) -> List[dict]:
    """Dated constraints plus structured recurring constraints from interview.

    Explicit dated rows win for the same person, date and shift. A recurring
    all-shifts rule is expanded per declared shift, which lets one dated shift
    exception override only that occurrence.
    """
    start, end = _parse_date(starts_on), _parse_date(ends_on)
    explicit = []
    for row in _bounded_rows(rows, 2000):
        date = _date_text(row.get("date") or row.get("constraint_date"))
        if not date:
            continue
        parsed = _parse_date(date)
        if start is not None and end is not None and (
            parsed is None or parsed < start or parsed > end
        ):
            continue
        explicit.append({
            "employee": _bounded(row.get("employee")),
            "date": date,
            "shift": _bounded(row.get("shift") or row.get("shift_name")),
            "available": bool(row.get("available")),
            "start_time": _bounded(row.get("start_time")),
            "end_time": _bounded(row.get("end_time")),
            "is_hard": row.get("is_hard", True) is not False,
            "reason": _bounded(row.get("reason")),
            "source": _bounded(row.get("source")),
        })
    if start is None or end is None or end < start:
        return explicit

    explicit_keys = {
        (row["employee"], row["date"], row["shift"]) for row in explicit
    }
    shift_names = [
        _bounded(shift.get("name"))
        for shift in (profile or {}).get("shifts") or []
        if isinstance(shift, dict) and _bounded(shift.get("name"))
    ]
    rotation = _rotation_availability(
        profile, start, end, explicit_keys
    )
    closure = _closure_availability(profile, start, end, explicit_keys)
    recurring = []
    for person in (profile or {}).get("employees") or []:
        if not isinstance(person, dict):
            continue
        employee = _bounded(person.get("name"))
        for rule in person.get("recurring_constraints") or []:
            if not employee or not isinstance(rule, dict):
                continue
            days = {
                _weekday_key(item) for item in rule.get("days") or []
                if _weekday_key(item)
            }
            offered_shifts = [
                value for value in (
                    _bounded(item) for item in rule.get("shifts") or []
                ) if value
            ]
            applicable_shifts = offered_shifts or shift_names or [""]
            day = start
            while day <= end:
                weekday = _weekday_key(_HEBREW_WEEKDAYS[day.weekday()])
                if not days or weekday in days:
                    date = day.isoformat()
                    for shift in applicable_shifts:
                        key = (employee, date, shift)
                        if key in explicit_keys or (
                            employee, date, ""
                        ) in explicit_keys:
                            continue
                        recurring.append({
                            "employee": employee,
                            "date": date,
                            "shift": shift,
                            "available": bool(rule.get("available")),
                            "start_time": _bounded(rule.get("start_time")),
                            "end_time": _bounded(rule.get("end_time")),
                            "is_hard": rule.get("is_hard", True) is not False,
                            "reason": _bounded(rule.get("reason")),
                            "source": _bounded(rule.get("source")) or "interview",
                        })
                day += datetime.timedelta(days=1)
    return rotation + closure + recurring + explicit


def _rotation_availability(
    profile: dict, start: datetime.date, end: datetime.date,
    explicit_keys: set,
) -> List[dict]:
    """Expand Rotation A once; Rotation B is its exact slot complement."""
    workplace = (profile or {}).get("workplace") or {}
    rules = workplace.get("rotation_a_unavailability") or []
    rules = [rule for rule in rules if isinstance(rule, dict)]
    if not rules:
        return []

    people = []
    for person in (profile or {}).get("employees") or []:
        if not isinstance(person, dict):
            continue
        pattern = _bounded(person.get("exit_pattern")) or _bounded(
            workplace.get("rotation_mode")
        ) or "round"
        group = _bounded(person.get("rotation_group"))
        name = _bounded(person.get("name"))
        if pattern == "round" and group in ("א", "ב") and name:
            people.append((name, group))

    result = []
    for slot in build_slots(profile, start.isoformat(), end.isoformat()):
        unavailable_a = _rotation_a_blocks(slot, rules)
        for employee, group in people:
            unavailable = unavailable_a if group == "א" else not unavailable_a
            if not unavailable:
                continue
            key = (employee, slot["slot_date"], slot["shift_name"])
            if key in explicit_keys or (
                employee, slot["slot_date"], ""
            ) in explicit_keys:
                continue
            result.append({
                "employee": employee,
                "date": slot["slot_date"],
                "shift": slot["shift_name"],
                "available": False,
                "start_time": "",
                "end_time": "",
                "is_hard": True,
                "reason": "סבב %s אינו זמין במועד זה" % group,
                "source": "rotation",
                "rotation_group": group,
                "derived_from": "rotation_a_unavailability",
            })
    return result



def _closures_for_model(profile: dict, starts_on: str, ends_on: str) -> List[dict]:
    """The period's closure cycle, per weekend, for the prompt."""
    start, end = _parse_date(starts_on), _parse_date(ends_on)
    if start is None or end is None:
        return []
    return rotation_cycle.schedule_for_model(profile, start, end)

def _closure_availability(
    profile: dict, start: datetime.date, end: datetime.date,
    explicit_keys: set,
) -> List[dict]:
    """Hard rows keeping each closure day inside the group that owns it.

    The rotation is the point of a closure. A scheduler that balances every
    day on its own merits will hand Saturday to whoever is under quota, which
    equalises a number nobody asked to equalise and breaks the cycle the unit
    planned its month around. So on a day some group is closing, everyone on
    a rotation who is *not* holding that day is marked unavailable, and the
    model chooses only among the people actually in.

    Derived from the anchored cycle in `rotation.py` rather than asked of the
    model, for the reason `audit.py` is code: which group closes on 12/09 is
    arithmetic ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

    Only people on a rotation are constrained. Someone with no pattern and no
    group -- a civilian, a reserve on call -- is untouched, because the cycle
    says nothing about them and inventing a rule would remove them from days
    they can genuinely work.

    Silent for a cycle the unit never anchored: without that pattern's
    round/triplet anchor (or the legacy fallback) there is no phase to enforce,
    and guessing one would put the wrong group in on the wrong weekend while
    looking authoritative.
    """
    people = [
        person for person in (profile or {}).get("employees") or []
        if isinstance(person, dict) and _bounded(person.get("name"))
    ]
    # Who is legitimately held on each date, and by which cycle. A person on
    # a rotation the profile never anchored contributes nothing here, so
    # their days simply stay unconstrained.
    holders, cycles, owners = {}, {}, {}
    on_rotation = {}
    # Which shifts a date's closure actually covers. Absent means the whole
    # day; a set means only those shifts, which is the Sunday handover. A
    # date carrying one closure that runs all day and another that ends at
    # the handover is a whole-day date, or the fuller closure would be cut
    # short by the shorter one sharing its Sunday.
    covered: Dict[str, Optional[set]] = {}
    for person in people:
        name = _bounded(person.get("name"))
        rows = rotation_cycle.closure_days(profile, person, start, end)
        on_rotation[name] = bool(rows) or _on_rotation(profile, person)
        for row in rows:
            holders.setdefault(row["date"], set()).add(name)
            if not row["until_handover"]:
                covered[row["date"]] = None
            elif covered.setdefault(row["date"], set()) is not None:
                covered[row["date"]].update(row["shifts"])
            # Only a real rotation displaces anybody. A blank cycle is
            # somebody out every weekend regardless of whose turn it is, so
            # their presence must not put a rotating group "out of turn".
            if row["cycle"]:
                cycles.setdefault(row["date"], set()).add(row["cycle"])
            # Cycle plus group, so the reason can say "תלתון ג" rather than
            # only naming a letter that means different things per cycle.
            if row["cycle"] and row["group"]:
                owners.setdefault(row["date"], set()).add(
                    (row["cycle"], row["group"])
                )
    if not holders:
        return []

    result = []
    for slot in build_slots(profile, start.isoformat(), end.isoformat()):
        date = slot["slot_date"]
        held = holders.get(date)
        if not held:
            # No group closes this date, so it is an ordinary working day and
            # the rotation has no claim on who works it.
            continue
        limit = covered.get(date)
        if limit is not None and slot["shift_name"] not in limit:
            # The Sunday after a closure, past its handover. The stretch is
            # over: the day belongs to whoever is being relieved onto it, so
            # the rotation stops speaking here rather than blocking a whole
            # date on the strength of one morning.
            continue
        for person in people:
            name = _bounded(person.get("name"))
            if name in held or not on_rotation.get(name):
                continue
            # A person whose own cycle is not the one closing today is not
            # being displaced by it -- a תלתון soldier is not off because the
            # round pair happens to be in.
            pattern = rotation_cycle.exit_pattern(profile, person)
            if _cycle_key(profile, person, pattern) not in cycles.get(date, set()):
                continue
            key = (name, date, slot["shift_name"])
            if key in explicit_keys or (name, date, "") in explicit_keys:
                continue
            result.append({
                "employee": name,
                "date": date,
                "shift": slot["shift_name"],
                "available": False,
                "start_time": "",
                "end_time": "",
                "is_hard": True,
                "reason": "%s סוגר במועד זה" % " ו".join(
                    sorted(
                        rotation_cycle.label(cycle, group)
                        for cycle, group in owners.get(date, set())
                    )
                ),
                "source": "closure",
                "rotation_group": _bounded(person.get("rotation_group")),
                "derived_from": "closure_cycle",
            })
    return result


def _on_rotation(profile: dict, person: dict) -> bool:
    """Whether the cycle has any claim on this person at all."""
    pattern = rotation_cycle.exit_pattern(profile, person)
    return (
        pattern in ("round", "triplet", "hamshushim", "shushim")
        and bool(_bounded(person.get("rotation_group")))
    )


def _cycle_key(profile: dict, person: dict, pattern: str) -> str:
    """The cycle a person turns on: their pattern, or their group's."""
    if pattern in ("round", "triplet"):
        return pattern
    if _bounded(person.get("rotation_group")) == "ג":
        return "triplet"
    mode = _bounded(
        ((profile or {}).get("workplace") or {}).get("rotation_mode")
    )
    return mode if mode in ("round", "triplet") else "round"


def _rotation_a_blocks(slot: dict, rules: List[dict]) -> bool:
    weekday = _weekday_key(slot.get("weekday"))
    for rule in rules:
        days = {
            _weekday_key(item) for item in rule.get("days") or []
            if _weekday_key(item)
        }
        if days and weekday not in days:
            continue
        shifts = {
            _bounded(item) for item in rule.get("shifts") or []
            if _bounded(item)
        }
        if shifts and slot.get("shift_name") not in shifts:
            continue
        assignment = {
            "employee": "rotation-a", "date": slot.get("slot_date"),
            "shift": slot.get("shift_name"),
            "start_time": slot.get("start_time"),
            "end_time": slot.get("end_time"),
        }
        constraint = {
            "employee": "rotation-a", "date": slot.get("slot_date"),
            "shift": slot.get("shift_name"), "available": False,
            "start_time": rule.get("start_time"),
            "end_time": rule.get("end_time"),
        }
        if constraint_conflicts(assignment, constraint):
            return True
    return False


def _role_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [role for role in (_bounded(item) for item in value) if role]


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
            "role": person.get("role") or person.get("roles") or "",
            "eligible_shifts": person.get("eligible_shifts") or [],
            "max_weekly_hours": person.get("max_weekly_hours") or 0,
            "is_trainee": bool(person.get("is_trainee")),
            "is_shift_manager": bool(person.get("is_shift_manager")),
            "can_train": bool(person.get("can_train")),
            "exit_pattern": person.get("exit_pattern") or "",
            "rotation_group": person.get("rotation_group") or "",
            "notes": person.get("notes") or "",
            # The audit's own rule, imported rather than restated: this is
            # what the model is told a shadow shift means, and the warning it
            # gets judged by has to mean the same thing.
            "counts_toward_staffing": counts_toward_staffing(person, profile),
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
                # Non-counting trainees may be assigned in addition to the
                # required headcount, so permit every legal candidate once.
                "maxItems": sum(
                    len(candidates["by_slot"].get("slot-%d" % index, []))
                    for index, _ in enumerate(slots, 1)
                ),
                "items": assignment,
            },
            "notes": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
    }


def _read_day_assignments(
    offered: Any, slots: List[dict], profile: dict, candidates: dict,
    availability: Optional[List[dict]] = None,
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
    accepted = _assignments(translated, slots, profile, availability)
    if len(accepted) < len(translated):
        rejected.extend(
            {"reason": "missing reason, duplicate, or unknown slot/person"}
            for _ in range(len(translated) - len(accepted))
        )
    return accepted, rejected


def _replace_span(
    existing: List[dict], incoming: List[dict], dates: set
) -> List[dict]:
    """What the roster looks like with these dates re-decided.

    Everything outside the span is kept exactly as it was — a span is
    re-answerable in isolation, which is what makes a failed one retryable
    without disturbing its neighbours.
    """
    return _merge(
        [row for row in existing if row.get("date") not in dates], incoming
    )


def _replace_day(existing: List[dict], incoming: List[dict], day: str) -> List[dict]:
    return _replace_span(existing, incoming, {day})


def _previous_day(assignments: List[dict], day: str) -> List[dict]:
    parsed = _parse_date(day)
    if parsed is None:
        return []
    yesterday = (parsed - datetime.timedelta(days=1)).isoformat()
    return _committed_for_model([
        row for row in assignments if row.get("date") == yesterday
    ])


def _audit_for_span(
    assignments: List[dict], slots: List[dict], profile: dict,
    availability: List[dict], dates: set,
) -> List[dict]:
    """Every warning that belongs to the dates just generated.

    A finding carrying no date at all is kept: it is true of the period the
    span sits in, and the manager reads these beside the schedule. What it is
    *not* is a finding about these dates — see `_span_warnings`, which is the
    caller that has to tell the difference.
    """
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
        if not item.get("date") or _bounded(item.get("date")) in dates
    ]


def _span_warnings(
    assignments: List[dict], slots: List[dict], profile: dict,
    availability: List[dict], candidates: dict, dates: set,
) -> List[dict]:
    """The subset a repair call could actually fix. Nothing else is worth one.

    **A finding with no date is not one of them.** `OVER_HOURS` is the case
    that matters: it is a *weekly* total, so it carries an employee and a
    week but no date, and it is produced by the days already committed rather
    than by the span being generated now. `_audit_for_span` keeps it (it is
    true, and the manager should see it), and this drops it, because the
    repair instruction says in so many words not to touch earlier dates —
    so asking is a second model call that cannot succeed.

    Before this distinction existed, one person crossing their weekly ceiling
    on a Wednesday bought a repair call on every remaining day of that week,
    for the rest of the period, none of which could ever clear it. On a month
    that is most of the build time, spent on a question already answered.
    """
    warnings = [
        item for item in _audit_for_span(
            assignments, slots, profile, availability, dates
        )
        if item.get("code") in _REPAIRABLE_WARNING_CODES
        and item.get("severity") == "warning"
        and _bounded(item.get("date")) in dates
    ]
    # Do not spend a repair call asking for impossible coverage. If a slot has
    # fewer legal candidates than seats, the honest outcome is an unfilled
    # warning for the manager.
    #
    # Counted in the people who actually fill a seat: a slot needing four with
    # three counting candidates and two trainees available is not fillable,
    # and asking the model to repair it burns a call it cannot answer.
    counting = {
        item["id"] for item in candidates["employees"]
        if item.get("counts_toward_staffing")
    }
    fillable = {}
    for index, slot in enumerate(slots, 1):
        available = len([
            employee_id
            for employee_id in candidates["by_slot"].get("slot-%d" % index, [])
            if employee_id in counting
        ])
        fillable[(slot["shift_name"], slot["slot_date"])] = available >= int(
            slot.get("headcount", 1)
        )
    return [
        item for item in warnings
        if item.get("code") != UNFILLED
        or fillable.get(
            (item.get("shift"), _bounded(item.get("date"))), False
        )
    ]


def _metrics(
    day: str, started: float, status: str, returned: int = 0,
    accepted: int = 0, rejected: int = 0, warnings: int = 0,
    repaired: bool = False, usage: Optional[dict] = None,
    through: str = "",
) -> dict:
    return {
        "date": day,
        # The last date this call covered. Equal to `date` on a single day,
        # so a reader that only knows about days still reads it correctly.
        "through": through or day,
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
        return datetime.date.fromisoformat(_date_text(value))
    except (ValueError, TypeError):
        return None


def _date_text(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _bounded(value)


__all__ = [
    "Scheduler", "SCHEDULE_RESPONSE_SCHEMA", "build_slots",
    "effective_availability", "plan_spans",
    "GENERATION_MODES", "MODE_DAY", "MODE_WEEK",
]
