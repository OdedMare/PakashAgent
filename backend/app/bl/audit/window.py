"""Which of a period's facts fall inside a span of dates.

The stats panel can be asked about a day, a week, a month or any range, and
none of those is a stored period. An assignment and a slot carry their date
and are compared directly. A warning is the one fact whose date takes
reading: most are pinned to a day, the weekly hours ceiling is pinned to an
ISO week, and what is left describes the period as a whole.
"""

import datetime
from typing import Optional, Tuple

from app.bl.audit.values import text


def in_window(date: str, start: str, end: str) -> bool:
    """ISO dates order as text, so the comparison needs no parsing."""
    return bool(date) and start <= date <= end


def warning_in_window(warning: dict, start: str, end: str) -> bool:
    """Whether a finding belongs to the span being counted.

    A warning carrying neither a date nor a week is kept: it came from a
    period that touches the span, and dropping it would make a finding
    disappear from the count while it is still printed under the calendar.
    """
    span = _span(warning)
    if span is None:
        return True
    return span[0] <= end and span[1] >= start


def _span(warning: dict) -> Optional[Tuple[str, str]]:
    date = text(warning.get("date"))
    if date:
        return date, date
    details = warning.get("details")
    details = details if isinstance(details, dict) else {}
    try:
        monday = datetime.date.fromisocalendar(
            int(details["year"]), int(details["week"]), 1
        )
    except (KeyError, TypeError, ValueError):
        return None
    sunday = monday + datetime.timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()
