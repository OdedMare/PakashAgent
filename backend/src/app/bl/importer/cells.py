"""Reading one cell: text, dates, people, availability markers, hours.

Hebrew is data here: weekday names, availability markers and two date formats
(`d/M/yy` and `d.M`, the latter with no year at all) are values to parse, not
text to display.
"""

import datetime
import re
from typing import Any, List

from app.common.time_context.time_context import israel_today

# Hebrew weekday names as the source files write them. They appear *inside*
# header cells ("2.2 ראשון") and are what disambiguates a date column from a
# stray number.
HEBREW_WEEKDAYS = ("ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת")

# Availability markers living in the assignment grid (Sample B). Matched as
# whole cell values after normalisation, never as substrings.
_UNAVAILABLE = ("לא זמין", "לא זמינה", "לא יכול", "לא יכולה", "חופש", "מחלה")

_DATE_PATTERNS = (
    ("%Y-%m-%d", r"^(\d{4})-(\d{1,2})-(\d{1,2})$"),
    ("%d/%m/%Y", r"^(\d{1,2})/(\d{1,2})/(\d{4})$"),
    ("%d/%m/%y", r"^(\d{1,2})/(\d{1,2})/(\d{2})$"),
    ("%d.%m.%Y", r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"),
    ("%d.%m.%y", r"^(\d{1,2})\.(\d{1,2})\.(\d{2})$"),
    ("%d-%m-%Y", r"^(\d{1,2})-(\d{1,2})-(\d{4})$"),
    ("%d-%m-%y", r"^(\d{1,2})-(\d{1,2})-(\d{2})$"),
)
# `d.M` with no year at all (Sample B). The year must come from context.
DAY_MONTH = re.compile(r"^(\d{1,2})[./](\d{1,2})$")
_EXCEL_EPOCH = datetime.date(1899, 12, 30)
_EXCEL_SERIALS = (20000, 80000)
_HOURS = re.compile(
    r"^(\d{1,2})[:.](\d{2})\s*(?:-|–|—|עד)\s*(\d{1,2})[:.](\d{2})$"
)
_LABEL_PUNCTUATION = " ,|-()׳״"


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value).strip()


def normalise(value: Any) -> str:
    """Trimmed, whitespace-collapsed text for comparison."""
    cleaned = text(value).translate({
        ord("‎"): None,
        ord("‏"): None,
        ord("﻿"): None,
        ord(" "): " ",
    })
    return re.sub(r"\s+", " ", cleaned).strip()


def is_weekday(value: Any) -> bool:
    return normalise(value) in HEBREW_WEEKDAYS


def without_weekday(value: Any) -> str:
    """A header cell with any weekday label stripped from it."""
    cleaned = normalise(value)
    for weekday in HEBREW_WEEKDAYS:
        cleaned = cleaned.replace("יום " + weekday, " ").replace(weekday, " ")
    return cleaned.strip(_LABEL_PUNCTUATION)


def parse_date(value: Any) -> str:
    """A header cell as an ISO date, or empty.

    Handles both source formats plus real `datetime` values and Excel serial
    numbers. A Hebrew weekday name may trail the date (`2.2 ראשון`) and is
    stripped before parsing.
    """
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()[:10]
    if isinstance(value, (int, float)) and not isinstance(value, bool) \
            and _excel_serial(value):
        return _excel_serial(value)
    cleaned = normalise(value)
    if not cleaned:
        return ""
    if re.match(r"^\d{5}(?:\.0+)?$", cleaned) and _excel_serial(float(cleaned)):
        return _excel_serial(float(cleaned))
    cleaned = without_weekday(cleaned)
    if not cleaned:
        return ""
    for fmt, pattern in _DATE_PATTERNS:
        if re.match(pattern, cleaned):
            try:
                return datetime.datetime.strptime(cleaned, fmt).date().isoformat()
            except ValueError:
                continue
    match = DAY_MONTH.match(cleaned)
    if match:
        return _resolve_year(int(match.group(1)), int(match.group(2)))
    return ""


def _excel_serial(value: float) -> str:
    if not _EXCEL_SERIALS[0] <= value <= _EXCEL_SERIALS[1]:
        return ""
    return (_EXCEL_EPOCH + datetime.timedelta(days=int(value))).isoformat()


def _resolve_year(day: int, month: int) -> str:
    """A `d.M` date with the year the file never wrote.

    Assuming the current year is the only defensible default without knowing
    the period being imported, and it is surfaced as a warning rather than
    applied silently.
    """
    try:
        return datetime.date(israel_today().year, month, day).isoformat()
    except ValueError:
        return ""


def is_yearless(value: Any) -> bool:
    return bool(DAY_MONTH.match(without_weekday(value)))


def parse_hours(value: str) -> str:
    """`07:00-15:00` normalised, or empty when the cell is not a time range.

    The same range gets written `7:00-15:00`, `07.00-15.00` and
    `07:00 - 15:00` across files by the same person in the same year.
    """
    match = _HOURS.match(normalise(value))
    if not match:
        return ""
    start_h, start_m, end_h, end_m = (int(part) for part in match.groups())
    if start_h > 23 or end_h > 23 or start_m > 59 or end_m > 59:
        return ""
    return "%02d:%02d-%02d:%02d" % (start_h, start_m, end_h, end_m)


def is_unavailable(value: str) -> bool:
    cleaned = normalise(value)
    return any(cleaned == marker or cleaned.startswith(marker) for marker in _UNAVAILABLE)


def split_names(value: str) -> List[str]:
    """One cell into the people it names.

    `export.py` writes several people into a cell newline-separated, and the
    manager's own files use commas or slashes. The unfilled marker it writes
    is not a person.
    """
    from app.bl.export.export import UNFILLED

    names = []
    for part in re.split(r"[\n,/;]+", value or ""):
        name = part.strip()
        if name and name != UNFILLED and not name.startswith("—"):
            names.append(name)
    return names


def human_date(iso: str) -> str:
    try:
        day = datetime.datetime.strptime(iso[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return iso
    return "%d.%d.%d" % (day.day, day.month, day.year)
