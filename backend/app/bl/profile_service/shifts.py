"""Validating the shift vocabulary: hours, staffing, and shift type."""

from typing import Any, List

from app.bl.profile_service.validation import named_rows, text, text_list, valid_time
from app.common.errors import AgentError

_SHIFT_TYPES = ("regular", "overlap", "on_call")


def shifts(rows: Any) -> List[dict]:
    return [_shift(row) for row in named_rows(rows, "משמרת")]


def _shift(row: dict) -> dict:
    for field in ("start_time", "end_time"):
        value = text(row.get(field))
        if value and not valid_time(value):
            raise AgentError("שעת המשמרת חייבת להיות בפורמט HH:MM")
        row[field] = value
    row["staffing"] = _staffing(row)
    shift_type = text(row.get("shift_type")) or (
        "on_call" if row.get("is_on_call") else "regular"
    )
    if shift_type not in _SHIFT_TYPES:
        raise AgentError("סוג המשמרת אינו תקין")
    row.update({
        "shift_type": shift_type,
        "purpose": text(row.get("purpose")),
        "is_on_call": shift_type == "on_call",
        "requires_shift_manager": bool(row.get("requires_shift_manager")),
        # The roles qualified to stand this shift; empty restricts nobody.
        "allowed_roles": list(dict.fromkeys(text_list(row.get("allowed_roles") or []))),
    })
    return row


def _staffing(row: dict) -> List[dict]:
    """The default staffing group first, then the per-day ones.

    A flat `headcount` is folded into the default group (the one naming no
    days), so the rest of the product reads one shape. A headcount of 0 is
    a real answer: the shift does not run on those days (`build_slots`
    opens no slot), so a shift can be off on the weekend, or run only then.
    """
    groups = [group for group in row.get("staffing") or [] if isinstance(group, dict)]
    default = next(
        (g for g in groups if not isinstance(g.get("days"), list) or not g["days"]), {}
    )
    flat = row.pop("headcount", None)
    headcount = _headcount(flat if flat not in (None, "") else default.get("headcount", 1))
    return [{
        "days": [],
        "headcount": headcount,
        "required_roles": default.get("required_roles") or [],
    }] + [dict(group, headcount=_headcount(group.get("headcount", headcount)))
          for group in groups if group.get("days")]


def _headcount(value) -> int:
    """0–100 people; 0 means the shift does not run."""
    if isinstance(value, bool):
        raise AgentError("מספר העובדים במשמרת חייב להיות מספר")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise AgentError("מספר העובדים במשמרת חייב להיות מספר")
    if not 0 <= number <= 100:
        raise AgentError("מספר העובדים במשמרת חייב להיות בין 0 ל-100")
    return number


def shift_item(item: dict) -> dict:
    """An agent-proposed shift, in the shape the editor writes."""
    return {
        "name": item.get("name"),
        "start_time": item.get("start_time") or "",
        "end_time": item.get("end_time") or "",
        "headcount": 1 if item.get("headcount") in (None, "") else item.get("headcount"),
        "is_on_call": bool(item.get("is_on_call")),
        "requires_shift_manager": bool(item.get("requires_shift_manager")),
    }
