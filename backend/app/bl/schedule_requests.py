"""Structured requests: what code can honour beyond pins and absences.

A pin (`required_assignment`) and an absence (`unavailable`) name one person,
one shift and one date. Most of what a manager actually asks for is wider
than that and often only a wish, so four more shapes exist:

| kind | meaning |
|---|---|
| `avoid` | the person should not work matching shifts |
| `prefer` | the person should work matching shifts (soft only) |
| `max_count` | at most `count` matching shifts, per period or per week |
| `not_together` | these people should not share a matching shift |

Every request is hard or soft. A hard one removes a candidate the way an
unavailability does; a soft one adds its `weight` to the candidate's cost,
and a `prefer` subtracts it. `shifts`, `dates` and `weekdays` narrow which
slots a request covers; left empty, each means "any".

`read_requests` is the one validator, used for requests passed in directly
and for those the model translated from the manager's sentences: every name
must be on the roster and every shift in the vocabulary (D9), so a request
can never introduce a person or shift nobody declared.

Its own module because both `scheduler/directives.py` (the translation
schema) and `deterministic_scheduler/` (honouring) read it, and those two
packages already import each other.
"""

import datetime
from typing import Any, List, Tuple

from app.bl.shared import HEBREW_WEEKDAYS, text, weekday_key

KINDS = ("avoid", "prefer", "max_count", "not_together")
PERIODS = ("period", "week")
_WEEKDAYS = frozenset(weekday_key(day) for day in HEBREW_WEEKDAYS)
_MAX_REQUESTS = 500


def read_requests(raw: Any, profile: dict) -> Tuple[List[dict], List[str]]:
    """Normalised requests plus a Hebrew error for each one refused."""
    if raw in (None, ""):
        return [], []
    if not isinstance(raw, list):
        return [], ["רשימת הבקשות אינה תקינה"]
    people = {
        text(row.get("name")) for row in (profile or {}).get("employees") or []
        if isinstance(row, dict) and text(row.get("name"))
    }
    shifts = {
        text(row.get("name")) for row in (profile or {}).get("shifts") or []
        if isinstance(row, dict) and text(row.get("name"))
    }
    result, errors = [], []
    for index, item in enumerate(raw[:_MAX_REQUESTS], start=1):
        request, problem = _read(item, people, shifts)
        if problem:
            errors.append("בקשה %d: %s" % (index, problem))
        else:
            result.append(request)
    return result, errors


def _read(item: Any, people: set, shifts: set) -> Tuple[dict, str]:
    if not isinstance(item, dict):
        return {}, "הבקשה אינה תקינה"
    kind = text(item.get("kind"))
    if kind not in KINDS:
        return {}, "סוג בקשה לא מוכר: %s" % (kind or "ריק")
    request = {
        "kind": kind,
        "employees": _names(item.get("employees") or item.get("employee")),
        "shifts": _names(item.get("shifts")),
        "dates": _names(item.get("dates")),
        "weekdays": [weekday_key(day) for day in _names(item.get("weekdays"))],
        "count": item.get("count"),
        "per": text(item.get("per")) or "period",
        "is_hard": item.get("is_hard", False) is True,
        "weight": item.get("weight"),
        "reason": text(item.get("reason")),
        "source_id": text(item.get("source_id")),
    }
    return request, _problem(request, people, shifts)


def _problem(request: dict, people: set, shifts: set) -> str:
    kind, names = request["kind"], request["employees"]
    unknown = [name for name in names if name not in people]
    if unknown:
        return "עובד/ת לא מוכר/ת בצוות: %s" % ", ".join(unknown)
    if kind == "not_together" and len(set(names)) < 2:
        return "בקשת הפרדה צריכה לפחות שני עובדים"
    if kind != "not_together" and len(names) != 1:
        return "הבקשה צריכה לציין עובד/ת אחד/ת בדיוק"
    unknown = [name for name in request["shifts"] if name not in shifts]
    if unknown:
        return "משמרת לא מוכרת: %s" % ", ".join(unknown)
    if any(not _is_date(day) for day in request["dates"]):
        return "תאריך לא תקין בבקשה"
    if any(day not in _WEEKDAYS for day in request["weekdays"]):
        return "יום בשבוע לא מוכר בבקשה"
    if kind == "prefer" and request["is_hard"]:
        return "העדפה היא תמיד רכה; לשיבוץ מחייב יש להשתמש בשיבוץ חובה"
    if kind == "max_count" and not _is_count(request["count"]):
        return "מגבלת כמות צריכה מספר שלם אי-שלילי"
    if request["per"] not in PERIODS:
        return "תקופת מגבלה לא מוכרת: %s" % request["per"]
    weight = request["weight"]
    if weight is None:
        request["weight"] = 1.0
    elif isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
        return "משקל הבקשה צריך להיות מספר חיובי"
    else:
        request["weight"] = float(weight)
    if not request["reason"]:
        request["reason"] = _default_reason(request)
    return ""


def covers(request: dict, shift: str, day: str) -> bool:
    """Whether `request` speaks about this shift on this date."""
    if request["shifts"] and shift not in request["shifts"]:
        return False
    if request["dates"] and day not in request["dates"]:
        return False
    if request["weekdays"]:
        parsed = _date(day)
        if parsed is None or weekday_key(HEBREW_WEEKDAYS[parsed.weekday()]) not in request["weekdays"]:
            return False
    return True


def week_of(day: str):
    """The Sunday opening the week `day` falls in, or None."""
    parsed = _date(day)
    if parsed is None:
        return None
    return parsed - datetime.timedelta(days=(parsed.weekday() + 1) % 7)


def _default_reason(request: dict) -> str:
    names = ", ".join(request["employees"])
    return {
        "avoid": "בקשה ש%s לא ישובץ/תשובץ במשמרות האלה",
        "prefer": "בקשה לשבץ את %s במשמרות האלה",
        "max_count": "מגבלת כמות משמרות ל%s",
        "not_together": "בקשה ש%s לא ישובצו יחד",
    }[request["kind"]] % names


def _names(value: Any) -> List[str]:
    values = value if isinstance(value, list) else [value]
    return [text(item) for item in values if text(item)]


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_date(value: str) -> bool:
    return _date(value) is not None


def _date(value: str):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


__all__ = ["KINDS", "PERIODS", "covers", "read_requests", "week_of"]
