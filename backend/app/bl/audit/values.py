"""Parsing helpers for the audit. A value that cannot be read counts as absent.

An unparseable time contributes no hours and no rest check rather than a
guessed one -- the audit reporting a number it invented would defeat the
entire reason it is not the model doing this.
"""

import datetime
from typing import Any, Optional

MINUTES_PER_HOUR = 60.0
MINUTES_PER_DAY = 24 * 60


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def number(value: Any, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def parse_date(value: Any) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def parse_time(value: Any) -> Optional[datetime.datetime]:
    """`HH:MM` as a datetime on a fixed day, for arithmetic only."""
    stated = text(value)
    if not stated:
        return None
    for shape in ("%H:%M", "%H:%M:%S", "%H"):
        try:
            parsed = datetime.datetime.strptime(stated, shape)
            return parsed.replace(year=2000, month=1, day=1)
        except ValueError:
            continue
    return None


def minutes(value: Any) -> Optional[int]:
    if isinstance(value, (datetime.datetime, datetime.time)):
        return value.hour * 60 + value.minute
    parsed = parse_time(value)
    if parsed is None:
        return None
    return parsed.hour * 60 + parsed.minute


def slot_date(slot: dict) -> str:
    """A slot date as an ISO string, however the row carried it.

    Repository rows come back as `datetime.date`; a caller building a grid in
    memory passes strings. Both are compared against assignment dates here.
    """
    value = slot.get("slot_date")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return text(value)


def person_name(employee: Any) -> str:
    """A roster entry's name, whether the entry is a dict or a bare name."""
    return text(employee.get("name") if isinstance(employee, dict) else employee)
