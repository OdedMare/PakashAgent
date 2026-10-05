"""Row and roster helpers for the deterministic day filler."""

from typing import Any, List, Optional


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def date_of(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return text(value)


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


def eligible(person: dict, shift: str) -> bool:
    allowed = person.get("eligible_shifts")
    return not isinstance(allowed, list) or not allowed or shift in allowed


def roles(person: dict) -> set:
    listed = person.get("roles")
    result = {text(role) for role in listed if text(role)} if isinstance(listed, list) else set()
    if text(person.get("role")):
        result.add(text(person.get("role")))
    return result


def employees(profile: dict) -> List[dict]:
    return [
        row for row in (profile or {}).get("employees") or []
        if isinstance(row, dict) and text(row.get("name"))
    ]
