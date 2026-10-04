"""Bounded readers shared by the pattern and correction counters."""

import datetime
from typing import Any, List, Optional

# Enough history to see a pattern, bounded because every row is counted
# several times and the tallies are what reach the model.
MAX_ROWS = 5000
MAX_TEXT_CHARS = 2000


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def bounded(value: Any, limit: int = MAX_TEXT_CHARS) -> str:
    return text(value)[:limit]


def bounded_rows(rows: Any, limit: int = MAX_ROWS) -> List[dict]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows[:limit] if isinstance(row, dict)]


def date_of(value: Any) -> Optional[datetime.date]:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.datetime.strptime(text(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def iso_or_blank(value: Optional[datetime.date]) -> str:
    return value.isoformat() if value is not None else ""
