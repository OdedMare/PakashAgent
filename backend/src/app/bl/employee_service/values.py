"""Reading the profile and the schedule defensively for the employee area."""

from typing import Any, List, Optional

from app.common.errors.errors import AgentError

# Logged against the change log when a manager rules on a request, so an
# approval is traceable in the same place every other change is (D4).
ACTION_REQUEST_APPROVED = "request_approved"
ACTION_REQUEST_REJECTED = "request_rejected"
# A swap the manager refused. The approval has no action of its own: applying
# it goes through the ordinary swap path in `schedule_service`, which appends
# `ACTION_SWAPPED` exactly as a manager-initiated swap does. Two log rows for
# one swap would make the history read as two moves.
ACTION_SWAP_REJECTED = "swap_rejected"


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def iso_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value)[:10]


def roster_names(profile: dict) -> List[str]:
    """Employee names as the interview recorded them.

    Read defensively: the profile is model-produced JSON, so a missing or
    differently-shaped field degrades to an empty roster rather than throwing
    on the login screen.
    """
    employees = (profile or {}).get("employees")
    if not isinstance(employees, list):
        return []
    names = []
    for item in employees:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def employees(profile: dict) -> List[dict]:
    rows = (profile or {}).get("employees")
    return rows if isinstance(rows, list) else []


def shifts(profile: dict) -> List[dict]:
    rows = (profile or {}).get("shifts")
    return rows if isinstance(rows, list) else []


def window(schedule: Optional[dict]) -> tuple:
    if not schedule:
        return None, None
    return (
        iso_date(schedule.get("starts_on")) or None,
        iso_date(schedule.get("ends_on")) or None,
    )


def find_assignment(schedule: dict, assignment_id: str) -> Optional[dict]:
    for row in (schedule or {}).get("assignments") or []:
        if row.get("id") == assignment_id:
            return row
    return None


def require_reason(reason: str, message: str) -> str:
    """The manager's stated reason, trimmed, or a refusal to proceed without one."""
    stated = (reason or "").strip()
    if not stated:
        raise AgentError(message)
    return stated
