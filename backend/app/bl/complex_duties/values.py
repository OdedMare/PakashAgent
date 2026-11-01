"""Validating what a commander types about a duty, in Hebrew."""

import datetime
from typing import Any, Dict, List, Optional

from app.bl.shared import HEBREW_WEEKDAYS, hebrew_weekday, text, weekday_key
from app.common.errors import AgentError

NAME_LIMIT = 40
NOTE_LIMIT = 200
MAX_SEATS = 50
MAX_WEIGHT = 5
# The widest span one read of the duty board returns: a month drawn as whole
# weeks, like the team's own board (`MAX_SPAN_DAYS`).
MAX_SPAN_DAYS = 62

_WEEKDAYS = {weekday_key(day) for day in HEBREW_WEEKDAYS}


def type_fields(payload: Dict[str, Any], partial: bool = False) -> Dict[str, Any]:
    """The columns a duty type's payload sets, checked. `partial` is a
    patch: only the keys present are read."""
    fields: Dict[str, Any] = {}
    if not partial or "name" in payload:
        name = text(payload.get("name"))
        if not name:
            raise AgentError("צריך לתת שם לתורנות")
        if len(name) > NAME_LIMIT:
            raise AgentError("שם התורנות ארוך מדי")
        fields["name"] = name
    if not partial or "seats" in payload:
        fields["seats"] = _integer(payload.get("seats", 1), 1, MAX_SEATS,
                                   "מספר החיילים בתורנות צריך להיות בין 1 ל־%d" % MAX_SEATS)
    if not partial or "weight" in payload:
        fields["weight"] = _integer(payload.get("weight", 1), 0, MAX_WEIGHT,
                                    "משקל התורנות צריך להיות בין 0 ל־%d" % MAX_WEIGHT)
    if not partial or "days" in payload:
        fields["days"] = _days(payload.get("days") or [])
    if "active" in payload:
        if not isinstance(payload["active"], bool):
            raise AgentError("מצב התורנות אינו תקין")
        fields["active"] = payload["active"]
    return fields


def _integer(value: Any, low: int, high: int, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise AgentError(message)
    return value


def _days(days: Any) -> List[str]:
    if not isinstance(days, list):
        raise AgentError("ימי התורנות צריכים להיות רשימה")
    keys = []
    for day in days:
        key = weekday_key(day)
        if key not in _WEEKDAYS:
            raise AgentError("יום לא מוכר: %s" % (text(day) or "?"))
        if key not in keys:
            keys.append(key)
    return keys


def parse_day(value: Any) -> datetime.date:
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(text(value)[:10])
    except ValueError:
        raise AgentError("התאריך אינו תקין")


def span(start: Any, end: Any) -> tuple:
    first, last = parse_day(start), parse_day(end)
    if first > last:
        raise AgentError("טווח התאריכים אינו תקין")
    if (last - first).days >= MAX_SPAN_DAYS:
        raise AgentError("טווח התאריכים ארוך מדי")
    return first, last


def runs_on(duty_type: dict, day: datetime.date) -> bool:
    days = duty_type.get("days") or []
    return not days or weekday_key(hebrew_weekday(day)) in days


def note(value: Any) -> str:
    clean = text(value)
    if len(clean) > NOTE_LIMIT:
        raise AgentError("ההערה ארוכה מדי")
    return clean


def roster_person(profile: Optional[dict], employee: str) -> Optional[dict]:
    for person in (profile or {}).get("employees") or []:
        if isinstance(person, dict) and text(person.get("name")) == employee:
            return person
    return None
