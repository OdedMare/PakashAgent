"""Finding a sheet's header: the date row, the nested shift row, lane labels."""

from typing import Dict, List, Optional, Tuple

from app.bl.importer.cells import is_unavailable, is_weekday, parse_date, split_names, text
from app.bl.importer.vocabulary import ShiftVocabulary

# How far a header row may sit from the top before we stop looking for it.
# Real files carry a title and a blank line above the grid -- `export.py`
# writes exactly that -- but a header ten rows down means the sheet is not
# the shape we think it is.
MAX_HEADER_SCAN = 10


def find_date_row(grid: List[List[str]]) -> Optional[Tuple[int, List[tuple]]]:
    """The row carrying the most parseable dates, near the top.

    One date is enough: a sheet covering a single day is a real thing a
    manager keeps. Ambiguity is handled by *preferring* the row with more
    dates, not by rejecting thin ones.
    """
    best = None
    for index, row in enumerate(grid[:MAX_HEADER_SCAN]):
        dates = [
            (column, parse_date(value))
            for column, value in enumerate(row) if parse_date(value)
        ]
        if dates and (best is None or len(dates) > len(best[1])):
            best = (index, dates)
    return best


def first_data_row(grid: List[List[str]], row_index: int, dates: List[tuple]) -> int:
    """The first row after the header, skipping a weekday line under it."""
    first = row_index + 1
    if first < len(grid) and is_weekday_row(grid[first], dates):
        first += 1
    return first


def is_weekday_row(row: List[str], dates: List[tuple]) -> bool:
    """Whether a row under the dates is the weekday line, not data."""
    hits = sum(
        1 for column, _iso in dates
        if column < len(row) and is_weekday(row[column])
    )
    return hits >= max(1, len(dates) // 2)


def find_nested_header(
    grid: List[List[str]], vocabulary: ShiftVocabulary
) -> Optional[Tuple[int, List[tuple]]]:
    """A date row directly above a shift row, dates spanning their shifts.

    Returns the shift row's index and one `(column, date, shift)` entry per
    column. Nested means several shift columns under one date; without that
    this is Sample A's two-row header, which the shift-major reader owns.
    """
    found = find_date_row(grid)
    if found is None:
        return None
    date_row, dates = found
    shift_row = date_row + 1
    if shift_row >= len(grid):
        return None
    by_column = dict(dates)
    columns = []
    for column, value in enumerate(grid[shift_row]):
        shift_name = vocabulary.match(value)
        iso = by_column.get(column) or _carried_date(by_column, column)
        if shift_name and iso:
            columns.append((column, iso, shift_name))
    per_date: Dict[str, int] = {}
    for _column, iso, _shift in columns:
        per_date[iso] = per_date.get(iso, 0) + 1
    if not columns or max(per_date.values()) < 2:
        return None
    return shift_row, columns


def _carried_date(by_column: Dict[int, str], column: int) -> str:
    """The nearest date at or left of a column.

    A fallback for a merged header openpyxl did not report as a range —
    some writers emit the spanned cells as genuinely empty instead.
    """
    for candidate in range(column, -1, -1):
        if candidate in by_column:
            return by_column[candidate]
    return ""


def lane_label(row: List[str], data_columns: List[int]) -> str:
    """The row's own label, taken only from outside the data columns.

    Reading the first non-empty cell anywhere would return an assignment as
    though it were the row's name.
    """
    claimed = set(data_columns)
    for column, value in enumerate(row):
        if column not in claimed and text(value):
            return text(value)
    return ""


def lane_from_cells(row: List[str], data_columns: List[int]) -> str:
    """Who a label-less lane belongs to, read from the names it holds.

    Sample B writes the person's name into the cell where they are placed, so
    the lane's identity *is* its names. An availability marker names nobody.
    """
    for column in data_columns:
        if column >= len(row):
            continue
        for name in split_names(row[column]):
            if not is_unavailable(name):
                return name
    return ""


def year_warnings(dates: List[str]) -> List[str]:
    """What the manager should look at twice before approving."""
    years = {iso[:4] for iso in dates if len(iso) >= 4}
    if len(years) > 1:
        return ["הקובץ מכיל תאריכים מיותר משנה אחת — ודא שהשנה נכונה"]
    return []
