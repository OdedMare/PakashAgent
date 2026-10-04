"""Hebrew weekday names, as the interview collects them and the files write them.

Hebrew is data here, not presentation: a shift's `days`, a staffing group's
`days` and a recurring constraint's `days` are all lists of these names, and
the scheduler, the audit and the export must agree on how to read them.
"""

import datetime
from typing import Any, Optional

# Monday-first, because that is what `date.weekday()` returns.
HEBREW_WEEKDAYS = (
    "יום שני", "יום שלישי", "יום רביעי", "יום חמישי",
    "יום שישי", "שבת", "יום ראשון",
)


def hebrew_weekday(day: Optional[datetime.date]) -> str:
    """`day`'s Hebrew name, or empty when there is no day."""
    if day is None:
        return ""
    return HEBREW_WEEKDAYS[day.weekday()]


def weekday_key(value: Any) -> str:
    """The weekday independent of the optional Hebrew ``יום`` prefix.

    Interview answers naturally contain both ``ראשון`` and ``יום ראשון``.
    They name the same day, and treating them as different silently removed
    every prefixed weekday except שבת from generated schedules.
    """
    value = value.strip() if isinstance(value, str) else ""
    return value[4:].strip() if value.startswith("יום ") else value


def runs_on(days: Any, weekday: str) -> bool:
    """Whether a `days` list includes `weekday`. Empty means every day."""
    if not isinstance(days, list) or not days:
        return True
    return weekday_key(weekday) in {weekday_key(item) for item in days}
