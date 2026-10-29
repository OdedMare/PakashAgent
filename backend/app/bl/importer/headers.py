"""Reading a header line: its dates, its shift names, a lane's own label."""

import datetime
from typing import Dict, List, Optional, Tuple

from app.bl.importer.cells import (
    is_unavailable, normalise, parse_date, split_names, text, weekday_index,
)
from app.common.time_context import israel_today

# How far from the top detection looks for a header. Real files carry a
# title and a blank line above the grid -- `export.py` writes exactly that.
MAX_HEADER_SCAN = 12

Columns = List[Tuple[int, str]]


def line_dates(row: List[str]) -> Columns:
    """`(column, iso)` for every cell of a line that is a real date."""
    return [(column, parse_date(value)) for column, value in enumerate(row)
            if parse_date(value)]


def line_weekdays(row: List[str]) -> List[Tuple[int, int]]:
    """`(column, weekday)` for every cell that is only a weekday name."""
    found = []
    for column, value in enumerate(row):
        index = weekday_index(value)
        if index is not None and not parse_date(value):
            found.append((column, index))
    return found


def header_dates(row: List[str], week_start: str = "") -> Tuple[Columns, str]:
    """The dates a header line stands for, and the week it assumed.

    Real dates win. A line of weekday names only is a weekly template: it
    is laid on the week starting `week_start` (a Sunday the manager named),
    else on the coming one, and the second value says which was assumed so
    the confirm screen can ask.
    """
    dates = line_dates(row)
    if dates:
        return dates, ""
    weekdays = line_weekdays(row)
    if not weekdays:
        return [], ""
    sunday = _sunday(week_start)
    found, offset, last = [], 0, -1
    for column, weekday in weekdays:
        # A second ראשון further along is the next week, not the same day.
        if weekday <= last:
            offset += 7
        last = weekday
        day = sunday + datetime.timedelta(days=weekday + offset)
        found.append((column, day.isoformat()))
    return found, sunday.isoformat()


def carried(dates: Columns, width: int) -> Dict[int, str]:
    """Every column under a date, the date carried right across blanks.

    A merged date cell openpyxl did not report as merged arrives as the date
    followed by empty cells; the shift columns under it still belong to it.
    """
    by_column = dict(dates)
    found, current = {}, ""
    first = min(by_column) if by_column else width
    for column in range(first, width):
        current = by_column.get(column, current)
        if current:
            found[column] = current
    return found


def is_weekday_row(row: List[str], columns: List[int]) -> bool:
    """Whether a line under the dates is the weekday line, not data."""
    hits = sum(1 for column in columns
               if column < len(row) and weekday_index(row[column]) is not None)
    return hits >= max(1, len(columns) // 2)


def is_date_row(row: List[str], columns: List[int]) -> bool:
    """Whether a line further down starts another block of dates.

    A month kept as four weeks stacked on one sheet repeats its header
    before every week; read as data, each repeat would be a person named
    "15/6/25".
    """
    hits = sum(1 for column in columns
               if column < len(row) and parse_date(row[column]))
    return hits >= max(1, (len(columns) + 1) // 2)


def lane_label(row: List[str], data_columns: List[int], label: Optional[int]) -> str:
    """A lane's own label: the named column, else the first cell outside
    the data columns. Reading the first non-empty cell anywhere would return
    an assignment as though it were the lane's name."""
    if label is not None:
        return text(row[label]) if label < len(row) else ""
    claimed = set(data_columns)
    for column, value in enumerate(row):
        if column not in claimed and text(value):
            return text(value)
    return ""


def lane_from_cells(row: List[str], data_columns: List[int], extra=()) -> str:
    """Whose a label-less lane is, read from the names it holds (Sample B)."""
    for column in data_columns:
        if column >= len(row):
            continue
        for name in split_names(row[column]):
            if not is_unavailable(name, extra):
                return name
    return ""


def year_warnings(dates: List[str]) -> List[str]:
    years = {iso[:4] for iso in dates if len(iso) >= 4}
    if len(years) > 1:
        return ["הקובץ מכיל תאריכים מיותר משנה אחת — ודא שהשנה נכונה"]
    return []


def is_title(value: str) -> bool:
    """A row header such as "משמרות" or "שם" -- a caption, not a lane."""
    return normalise(value) in ("משמרות", "משמרת", "שם", "שמות", "עובד", "עובדים", "שם העובד")


def _sunday(week_start: str) -> datetime.date:
    try:
        day = datetime.date.fromisoformat((week_start or "")[:10])
    except ValueError:
        day = israel_today()
        day += datetime.timedelta(days=(6 - day.weekday()) % 7 or 7)
    # Python counts Monday as 0; the Hebrew week opens on Sunday.
    return day - datetime.timedelta(days=(day.weekday() + 1) % 7)
