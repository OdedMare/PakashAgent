"""Row and roster helpers for the solver."""

from typing import Any, List, Optional

from app.bl.rotation.vocabulary import cycle_of_group
from app.bl.shared import iso as date_of, person_roles, role_qualified, text


def assignment(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    employee = text(raw.get("employee"))
    shift = text(raw.get("shift") or raw.get("shift_name"))
    date = date_of(raw.get("date") or raw.get("slot_date"))
    if not employee or not shift or not date:
        return None
    return {"employee": employee, "shift": shift, "date": date, "reason": text(raw.get("reason"))}


def unique(rows: List[dict]) -> List[dict]:
    result, seen = [], set()
    for row in rows:
        key = (row["employee"], row["shift"], row["date"])
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def same_slot(row: dict, slot: dict) -> bool:
    return (
        text(row.get("shift")) == text(slot.get("shift_name") or slot.get("shift"))
        and date_of(row.get("date")) == date_of(slot.get("slot_date") or slot.get("date"))
    )


def eligible(person: dict, shift: str, definition: Optional[dict] = None,
             declared: Optional[list] = None, shadow: bool = False) -> bool:
    """The person's own `eligible_shifts`, then the shift's `allowed_roles`."""
    allowed = person.get("eligible_shifts")
    if isinstance(allowed, list) and allowed and shift not in allowed:
        return False
    return role_qualified(person, definition, declared, shadow)


def roles(person: dict) -> set:
    return person_roles(person)


def cycle_of(profile: dict, group: str) -> str:
    """Which cycle a rotation group runs when the person states none."""
    return cycle_of_group(profile, group)


def employees(profile: dict) -> List[dict]:
    return [
        row for row in (profile or {}).get("employees") or []
        if isinstance(row, dict) and text(row.get("name"))
    ]
