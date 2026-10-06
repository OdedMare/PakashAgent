"""Reading the stored schedule and the roster the way the placement checks do."""

import datetime
from typing import Any, Dict, List, Optional

from app.bl.audit.stats import shift_stats


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return text(value)


def parse(value: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def pretty(hours: float) -> str:
    """A round number without its trailing zero. 8.0 reads as 8."""
    return "%g" % round(hours, 1)


def employees(profile: dict) -> List[dict]:
    rows = (profile or {}).get("employees")
    return [row for row in rows or [] if isinstance(row, dict)]


def shifts(profile: dict) -> List[dict]:
    rows = (profile or {}).get("shifts")
    return [row for row in rows or [] if isinstance(row, dict)]


def rows(schedule: dict, drop: str = "") -> List[dict]:
    """The schedule's assignments as audit rows, optionally without one.

    `drop` is the assignment being moved. Removing it is what makes a move
    check as a move: left in, the person is momentarily in two places and
    every drag would report a double-booking it is about to resolve.
    """
    return [
        {
            "employee": text(row.get("employee")),
            "shift": text(row.get("shift")),
            "date": iso(row.get("date")),
        }
        for row in (schedule or {}).get("assignments") or []
        if isinstance(row, dict) and not (drop and text(row.get("id")) == drop)
    ]


def slots(schedule: dict) -> List[dict]:
    """The stored grid, dates normalized -- passed to `audit()` so an
    entirely unstaffed shift is still visible."""
    return [
        dict(slot, slot_date=iso(slot.get("slot_date")))
        for slot in (schedule or {}).get("slots") or [] if isinstance(slot, dict)
    ]


def is_eligible(profile: dict, employee: str, shift_name: str, date: str = "") -> bool:
    """Whether the profile says this person works this shift.

    A roster that declares no `eligible_shifts` for somebody is saying
    nothing, not saying no. Somebody on the grid the roster no longer carries
    is not relitigated here either.
    """
    for person in employees(profile):
        if text(person.get("name")) != employee:
            continue
        if date and person.get("inactive_from") and date >= person["inactive_from"]:
            return False
        active_shifts = {row.get("name") for row in shifts(profile)}
        if shift_name not in active_shifts and shift_name in (person.get("archived_eligible_shifts") or []):
            return True
        eligible = person.get("eligible_shifts")
        if not isinstance(eligible, list) or not eligible:
            return True
        return shift_name in [text(item) for item in eligible]
    return True


def hours_by_employee(schedule: dict, profile: dict) -> Dict[str, float]:
    """Assigned hours per person in this period, weighted as the audit does.

    `audit.roster.shift_hours` is the one hours calculation in the product,
    so a candidate's "8 hours" here is the same number the warning uses.
    """
    stats = shift_stats(schedule.get("assignments") or [], shifts(profile), employees(profile),
                        slots=schedule.get("slots") or [], profile=profile)
    return {row["employee"]: row["hours"] for row in stats["by_employee"]}


def warning_key(warning: dict) -> tuple:
    """What makes two warnings the same warning.

    The message is deliberately out of it: the over-hours check writes the
    running total into its sentence, so a placement pushing somebody from 46
    to 54 hours would otherwise read as a brand-new warning.
    """
    return (
        text(warning.get("code")),
        text(warning.get("employee")),
        text(warning.get("date")),
        text(warning.get("shift")),
    )
