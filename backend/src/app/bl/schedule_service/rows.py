"""Pure projections of stored rows into the shapes callers and contracts read.

No repository and no model: every function here maps a dict to a dict, which
is what lets each collaborator share one spelling of "a date as a string" or
"an availability row as the audit reads it" instead of restating it.
"""

import datetime
from typing import Any, List, Optional


def iso(value: Any) -> str:
    """Dates arrive as `datetime.date` from SQL and as strings from the model."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value.strip() if isinstance(value, str) else ""


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def now_stamp() -> str:
    """This instant, UTC, as the browser will parse it.

    A `Z` suffix rather than `+00:00` because the value is read by
    `Date.parse` in the poller, and a bare naive string there is read as
    *local* time -- which would make a fresh heartbeat look hours stale to a
    manager in Israel and stall a job that is working perfectly.
    """
    stamp = datetime.datetime.now(datetime.timezone.utc)
    return stamp.replace(microsecond=0, tzinfo=None).isoformat() + "Z"


def window(schedule: Optional[dict]) -> tuple:
    """The date range a schedule covers, as ISO strings."""
    if not schedule:
        return None, None
    return iso(schedule.get("starts_on")), iso(schedule.get("ends_on"))


def employees(profile: dict) -> List[dict]:
    people = (profile or {}).get("employees")
    return [row for row in people or [] if isinstance(row, dict)]


def shifts(profile: dict) -> List[dict]:
    declared = (profile or {}).get("shifts")
    return [row for row in declared or [] if isinstance(row, dict)]


def has_shifts(profile: dict) -> bool:
    """Whether this profile can produce a grid at all.

    Deliberately the same test `build_slots` applies -- a dict with a usable
    name -- rather than merely `profile["shifts"]` being non-empty. A shift
    the builder silently skips is, for the manager pressing the button,
    identical to one that was never declared, and a gate that disagreed with
    the builder would let exactly that case through to an empty grid and a
    502 with nothing to act on. That was the original bug.
    """
    return any(
        isinstance(shift, dict) and (shift.get("name") or "").strip()
        for shift in (profile or {}).get("shifts") or []
    )


def workplace_name(profile: dict) -> str:
    workplace = (profile or {}).get("workplace")
    if isinstance(workplace, dict) and isinstance(workplace.get("name"), str):
        return workplace["name"].strip()
    return ""


def assignment_fact(row: dict) -> dict:
    """An assignment as the audit counts it: who, which shift, which date."""
    return {
        "employee": row.get("employee"),
        "shift": row.get("shift"),
        "date": iso(row.get("date")),
    }


def assignment_facts(rows: Optional[List[dict]]) -> List[dict]:
    return [assignment_fact(row) for row in rows or []]


def availability_fact(row: dict, with_reason: bool = True) -> dict:
    """A stored availability row in the shape `audit`/`placement` read."""
    fact = {
        "employee": row.get("employee"),
        "date": iso(row.get("constraint_date")),
        "shift": row.get("shift_name") or "",
        "available": row.get("available"),
        "start_time": row.get("start_time") or "",
        "end_time": row.get("end_time") or "",
        "is_hard": row.get("is_hard", True),
    }
    if with_reason:
        fact["reason"] = row.get("reason") or ""
    return fact


def audit_slot(slot: dict) -> dict:
    """A stored slot carrying what the audit needs to grade it.

    `headcount` travels with it because the grid is what the number was
    worked out into. Projecting it away left the audit to recompute the
    requirement from today's profile, which is a different number on any
    shift whose standard changes across the week and on any period imported
    from a file.
    """
    return {
        "shift_name": slot.get("shift_name"),
        "slot_date": iso(slot.get("slot_date")),
        "required_roles": slot.get("required_roles") or [],
        "headcount": slot.get("headcount"),
        "requires_shift_manager": slot.get("requires_shift_manager"),
    }


def stats_slot(slot: dict) -> dict:
    return {
        "shift_name": slot.get("shift_name"),
        "slot_date": iso(slot.get("slot_date")),
        "headcount": slot.get("headcount"),
    }


def period_row(row: dict) -> dict:
    """One row of the period list, with its dates as strings."""
    return dict(
        row,
        starts_on=iso(row.get("starts_on")),
        ends_on=iso(row.get("ends_on")),
    )


def change_row(row: dict) -> dict:
    """One change-log row, with its date and timestamp as strings.

    `created_at` is a `datetime`, not a `date`, and `iso` handles both --
    anything carrying `isoformat` comes back as text.
    """
    return dict(
        row,
        slot_date=iso(row.get("slot_date")) or None,
        created_at=iso(row.get("created_at")) or None,
    )


def dated(schedule: dict) -> dict:
    """Every date in a schedule as an ISO string.

    The repository returns real `DATE` columns, so a schedule read straight
    back out carries `datetime.date` objects while the HTTP contract declares
    strings. Pydantic refuses those on the way out, which turns an otherwise
    successful write into a 500 -- and only on the routes that re-read what
    they just stored, which is why the fake-repository tests (storing strings
    throughout) never saw it.

    Normalised in the one place every schedule-carrying response passes
    through: a route added later gets this for free instead of rediscovering
    the bug.
    """
    schedule["starts_on"] = iso(schedule.get("starts_on"))
    schedule["ends_on"] = iso(schedule.get("ends_on"))
    schedule["slots"] = [
        dict(slot, slot_date=iso(slot.get("slot_date")))
        for slot in schedule.get("slots") or []
    ]
    schedule["assignments"] = [
        dict(row, date=iso(row.get("date")))
        for row in schedule.get("assignments") or []
    ]
    return schedule


def slot_index(slots: List[dict]) -> dict:
    """(shift name, ISO date) -> slot id, for placing rows onto a grid."""
    return {
        (text(slot.get("shift_name")), iso(slot.get("slot_date"))): slot["id"]
        for slot in slots or []
    }


def find_assignment(schedule: dict, assignment_id: str) -> Optional[dict]:
    for row in schedule.get("assignments") or []:
        if row.get("id") == assignment_id:
            return row
    return None


def quiet_briefing() -> dict:
    """A briefing with nothing to say.

    The shape a caller gets when the agent cannot speak -- no profile yet, or
    the model failed. Identical to the shape it returns when it genuinely has
    nothing to report, so the UI has one case to render and a briefing that
    could not be produced never surfaces as an error beside the calendar.
    """
    return {"headline": "", "items": [], "quiet": True}
