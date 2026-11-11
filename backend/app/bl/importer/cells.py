"""Reading one cell: text, dates, people, availability markers, hours.

Hebrew is data here: weekday names, availability markers and two date formats
(`d/M/yy` and `d.M`, the latter with no year at all) are values to parse, not
text to display.
"""

import contextvars
import datetime
import functools
import re
from typing import Any, Iterable, Optional

from app.common.time_context import israel_today

# Hebrew weekday names as the source files write them. They appear *inside*
# header cells ("2.2 ראשון") and are what disambiguates a date column from a
# stray number.
HEBREW_WEEKDAYS = ("ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת")
# The letter form a weekly template writes instead ("א׳", "ב'"), Sunday first.
_WEEKDAY_LETTERS = ("א", "ב", "ג", "ד", "ה", "ו", "ש")
_GERESH = "׳'`"

# Day, month and year in either order: which one a file meant is settled
# per header line (`month_first`), never per cell.
_NUMERIC_DATE = re.compile(r"^(\d{1,2})([/.\-])(\d{1,2})(?:\2(\d{2}|\d{4}))?$")

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

# A day and a Hebrew month, as Excel on a Hebrew locale displays a date:
# "01-מרץ", "28-פבר", "1 במרץ 2026". Months by their first three letters.
_HEBREW_MONTHS = {
    "ינו": 1, "פבר": 2, "מרץ": 3, "מרס": 3, "אפר": 4, "מאי": 5, "יונ": 6,
    "יול": 7, "אוג": 8, "ספט": 9, "אוק": 10, "נוב": 11, "דצמ": 12,
}
_DAY_HEBREW_MONTH = re.compile(
    r"^(\d{1,2})[\s\-./]*ב?([\u05d0-\u05ea]{3})[\u05d0-\u05ea]*(?:[\s\-./,]+(\d{2}|\d{4}))?$")

# The year the manager says a yearless sheet is in, for one read. A context
# variable rather than an argument threaded through every header helper.
YEAR_HINT: contextvars.ContextVar = contextvars.ContextVar("import_year_hint", default=0)
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
    return weekday_index(value) is not None


def weekday_index(value: Any) -> Optional[int]:
    """0 for Sunday ... 6 for Saturday when the cell is only a weekday.

    A weekly template heads its columns "ראשון", "יום שני" or "ג׳" and no
    date at all; the period it describes is then the manager's to name.
    """
    cleaned = normalise(value)
    if cleaned.startswith("יום "):
        cleaned = cleaned[4:].strip()
    if cleaned in HEBREW_WEEKDAYS:
        return HEBREW_WEEKDAYS.index(cleaned)
    if len(cleaned) == 2 and cleaned[1] in _GERESH and cleaned[0] in _WEEKDAY_LETTERS:
        return _WEEKDAY_LETTERS.index(cleaned[0])
    return None


def without_weekday(value: Any) -> str:
    """A header cell with any weekday label stripped from it."""
    cleaned = normalise(value)
    for weekday in HEBREW_WEEKDAYS:
        cleaned = cleaned.replace("יום " + weekday, " ").replace(weekday, " ")
    return cleaned.strip(_LABEL_PUNCTUATION)


def parse_date(value: Any, month_first: bool = False) -> str:
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
    found = _parse_text(value if isinstance(value, str) else str(value), month_first)
    if found.startswith(_YEARLESS):
        # Resolved outside the cache: which year is nearest moves with today.
        day, month = found[len(_YEARLESS):].split(".")
        return _resolve_year(int(day), int(month))
    return found


@functools.lru_cache(maxsize=8192)
def _parse_text(value: str, month_first: bool) -> str:
    """`parse_date` for text, kept: a sheet repeats the same few hundred
    values -- names, "בית", the dates -- across every layout tried."""
    cleaned = normalise(value)
    if not cleaned:
        return ""
    if re.match(r"^\d{5}(?:\.0+)?$", cleaned) and _excel_serial(float(cleaned)):
        return _excel_serial(float(cleaned))
    cleaned = without_weekday(cleaned)
    if not cleaned:
        return ""
    if month_first:
        cleaned = _swapped(cleaned)
    for fmt, pattern in _DATE_PATTERNS:
        if re.match(pattern, cleaned):
            try:
                return datetime.datetime.strptime(cleaned, fmt).date().isoformat()
            except ValueError:
                continue
    match = DAY_MONTH.match(cleaned)
    if match:
        return "%s%d.%d" % (_YEARLESS, int(match.group(1)), int(match.group(2)))
    return _hebrew_month_date(cleaned)


def _hebrew_month_date(cleaned: str) -> str:
    match = _DAY_HEBREW_MONTH.match(cleaned)
    month = _HEBREW_MONTHS.get(match.group(2)) if match else None
    if not month:
        return ""
    day, year = int(match.group(1)), match.group(3)
    if not year:
        return "%s%d.%d" % (_YEARLESS, day, month)
    year_number = int(year) + (2000 if len(year) == 2 else 0)
    try:
        return datetime.date(year_number, month, day).isoformat()
    except ValueError:
        return ""


_YEARLESS = "yearless:"


def _swapped(cleaned: str) -> str:
    """`10/13/2024` written day first, so the patterns below read it."""
    match = _NUMERIC_DATE.match(cleaned)
    if not match:
        return cleaned
    first, separator, second, year = match.groups()
    return separator.join(part for part in (second, first, year) if part)


def month_first(values: Iterable[Any]) -> bool:
    """Whether a line of dates is written month first (`10/13/2024`).

    An Israeli sheet writes the day first, and that is the default; Excel on
    an American locale writes the month first, and `10/12/2024` reads as two
    different days depending on which. The line settles it: a part above 12
    can only be a day, and failing that, the order that makes the dates run
    on from one column to the next is the one the file meant.
    """
    pairs = []
    for value in values:
        if not isinstance(value, str):
            continue
        match = _NUMERIC_DATE.match(without_weekday(value))
        if match:
            pairs.append((int(match.group(1)), int(match.group(3))))
    if any(first > 12 for first, _second in pairs):
        return False
    if any(second > 12 for _first, second in pairs):
        return True
    return _runs_on(values, True) > _runs_on(values, False)


def _runs_on(values: Iterable[Any], swapped: bool) -> int:
    """How many neighbouring dates follow on within a week, read one way."""
    found = [parse_date(value, swapped) for value in values if isinstance(value, str)]
    days = [datetime.date.fromisoformat(day) for day in found if day]
    return sum(1 for before, after in zip(days, days[1:]) if 0 <= (after - before).days <= 7)


def _excel_serial(value: float) -> str:
    if not _EXCEL_SERIALS[0] <= value <= _EXCEL_SERIALS[1]:
        return ""
    return (_EXCEL_EPOCH + datetime.timedelta(days=int(value))).isoformat()


def _resolve_year(day: int, month: int) -> str:
    """A `d.M` date with the year the file never wrote.

    The year that puts the date nearest today: a December sheet read in
    January is last year's, a January one read in December next year's.
    Surfaced as a warning rather than applied silently.
    """
    hint = YEAR_HINT.get()
    if hint:
        try:
            return datetime.date(hint, month, day).isoformat()
        except ValueError:
            return ""
    today = israel_today()
    found = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            found.append(datetime.date(year, month, day))
        except ValueError:
            continue
    if not found:
        return ""
    return min(found, key=lambda date: abs((date - today).days)).isoformat()


def is_yearless(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return _parse_text(value, False).startswith(_YEARLESS) \
        or _parse_text(value, True).startswith(_YEARLESS)


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


def human_date(iso: str) -> str:
    try:
        day = datetime.datetime.strptime(iso[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return iso
    return "%d.%d.%d" % (day.day, day.month, day.year)
