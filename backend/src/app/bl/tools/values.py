"""Small projections shared by the tools: names, dates, a period's identity."""

from typing import Any, List, Optional

from app.common.time_context import israel_today


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return text(value)


def number(value: Any, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def employees(profile: dict) -> List[dict]:
    rows = (profile or {}).get("employees")
    return [row for row in rows or [] if isinstance(row, dict)]


def shifts(profile: dict) -> List[dict]:
    rows = (profile or {}).get("shifts")
    return [row for row in rows or [] if isinstance(row, dict)]


def eligible(person: dict) -> List[str]:
    """The shifts this person works, or empty for "no restriction stated".

    Empty means unrestricted, matching `placement`: reading silence as a
    restriction would report every placement in a workplace that never
    answered.
    """
    rows = person.get("eligible_shifts")
    return [text(row) for row in rows] if isinstance(rows, list) else []


def window(schedule: Optional[dict]) -> tuple:
    """The date range a period covers, for reading constraints over it."""
    if not schedule:
        today = israel_today().isoformat()
        return today, today
    return iso(schedule.get("starts_on")), iso(schedule.get("ends_on"))


def period_view(schedule: dict) -> dict:
    """A period as a tool answer carries it: identity and bounds, no rows.

    A tool answer that carried the whole grid would put the same wall of JSON
    back in front of the model that having tools was meant to take away.
    """
    return {
        "id": text(schedule.get("id")),
        "starts_on": iso(schedule.get("starts_on")),
        "ends_on": iso(schedule.get("ends_on")),
        "status": text(schedule.get("status")),
        "slot_count": len(schedule.get("slots") or []),
        "assignment_count": len(schedule.get("assignments") or []),
    }


def audit_assignments(schedule: Optional[dict]) -> List[dict]:
    return [
        {
            "employee": text(row.get("employee")),
            "shift": text(row.get("shift")),
            "date": iso(row.get("date")),
        }
        for row in (schedule or {}).get("assignments") or []
    ]


def assignment_id(
    schedule: dict, employee: str, shift_name: str, slot_date: str
) -> str:
    """The row this person holds on this slot, if they hold one."""
    for row in (schedule or {}).get("assignments") or []:
        if (text(row.get("employee")) == employee
                and text(row.get("shift")) == shift_name
                and iso(row.get("date")) == slot_date):
            return text(row.get("id"))
    return ""
