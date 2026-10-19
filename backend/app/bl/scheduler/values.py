"""Defensive readers for values arriving from a profile or a model answer."""

import datetime
from typing import Any, List, Optional

MAX_HISTORY_ROWS = 400

from app.bl.shared import bounded, dict_rows as bounded_rows

__all__ = [
    "MAX_HISTORY_ROWS", "bounded", "bounded_rows", "date_text",
    "dates_between", "lines", "named", "parse_date", "role_list",
]


def lines(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [line for line in (bounded(item) for item in value) if line]


def role_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [role for role in (bounded(item) for item in value) if role]


def date_text(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return bounded(value)


def parse_date(value: Any) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(date_text(value))
    except (ValueError, TypeError):
        return None


def named(items: Any) -> List[dict]:
    """The dict entries of a profile list that carry a usable `name`."""
    return [
        item for item in items or []
        if isinstance(item, dict) and bounded(item.get("name"))
    ]


def dates_between(start: datetime.date, end: datetime.date) -> List[datetime.date]:
    days, day = [], start
    while day <= end:
        days.append(day)
        day += datetime.timedelta(days=1)
    return days
