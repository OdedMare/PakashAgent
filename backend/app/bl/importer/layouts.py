"""The three layouts a sheet can have, each read by its own class.

Not variants of one parser: shift-major reads lanes as shifts and cells as
people, person-major reads lanes as people and cells as placements, and
date-only has no shift axis at all. Each returns `(explained cells,
Interpretation)` or None, and `inference.py` scores them against each other.
"""

from typing import List, Optional, Tuple

from app.bl.importer.cells import is_unavailable, split_names
from app.bl.importer.files import MAX_ROWS
from app.bl.importer.headers import (
    find_date_row, find_nested_header, first_data_row, lane_from_cells,
    lane_label, year_warnings,
)
from app.bl.importer.interpretation import Interpretation
from app.bl.importer.vocabulary import ShiftVocabulary

# The row-header label Sample A puts above the shift column. Evidence for
# shift-major, never a requirement.
_SHIFT_HEADER_HINTS = ("משמרות", "משמרת")
_UNOWNED_NOTE = "%d סימוני אי־זמינות אינם משויכים לאדם — השלם את השם לפני האישור"
_ORPHANS_NOTE = (
    "%d סימוני אי-זמינות בקובץ אינם משויכים לאדם — השלם את השם לפני האישור"
)

Scored = Optional[Tuple[int, Interpretation]]


class CellCollector:
    """Classifies cells: a name becomes an assignment, a marker an absence.

    Availability and assignments share one grid, so every cell is
    *classified* rather than read.
    """

    def __init__(self):
        self.assignments: List[dict] = []
        self.unavailability: List[dict] = []
        self.people: List[str] = []
        self.explained = 0

    def take(self, value: str, date: str, shift: str, owner: str = "") -> None:
        if not value:
            return
        self.explained += 1
        for name in split_names(value):
            if is_unavailable(name):
                self.unavailability.append({
                    "employee": owner, "date": date, "shift": shift, "reason": name,
                })
                continue
            self.assignments.append({"employee": name, "shift": shift, "date": date})
            self.add_person(name)

    def add_person(self, name: str) -> None:
        if name and name not in self.people:
            self.people.append(name)

    def orphans(self) -> int:
        return len([row for row in self.unavailability if not row["employee"]])


class LayoutReader:
    layout = ""

    def read(self, grid: List[List[str]], vocabulary: ShiftVocabulary) -> Scored:
        raise NotImplementedError

    def _result(
        self, cells: CellCollector, shifts: List[str], dates: List[str],
        notes: List[str],
    ) -> Tuple[int, Interpretation]:
        return cells.explained, Interpretation(
            layout=self.layout,
            shifts=shifts,
            people=sorted(cells.people),
            dates=dates,
            assignments=cells.assignments,
            unavailability=cells.unavailability,
            warnings=notes,
        )


def _cell(row: List[str], column: int) -> str:
    return row[column] if column < len(row) else ""


class ShiftMajorReader(LayoutReader):
    """Sample A: dates across the top, shifts down the side, people in cells."""

    layout = "shift_major"

    def read(self, grid, vocabulary) -> Scored:
        header = find_date_row(grid)
        if header is None:
            return None
        row_index, dates = header
        columns = [column for column, _iso in dates]
        cells, shifts = CellCollector(), []
        for row in grid[first_data_row(grid, row_index, dates):MAX_ROWS]:
            label = lane_label(row, columns)
            if not label or label in _SHIFT_HEADER_HINTS:
                continue
            shift_name = vocabulary.match(label)
            # A row whose *cells* are shift names is a header, not a lane of
            # people -- reading it would invent a person per shift name.
            if not shift_name or vocabulary.mostly_shifts(row, dates):
                continue
            if shift_name not in shifts:
                shifts.append(shift_name)
            for column, iso in dates:
                cells.take(_cell(row, column), iso, shift_name)
        if not shifts or not cells.assignments:
            return None
        iso_dates = [iso for _column, iso in dates]
        notes = year_warnings(iso_dates)
        if cells.unavailability:
            notes.append(_UNOWNED_NOTE % len(cells.unavailability))
        return self._result(cells, shifts, iso_dates, notes)


class PersonMajorReader(LayoutReader):
    """Sample B: a nested `date x shift` header, one lane per person.

    A lane's person comes from a label column where the sheet has one, and
    otherwise from the names inside the row. A lane holding only markers is
    recorded with an empty employee and warned about rather than dropped: an
    unattributed constraint is still a fact about the period (D7).
    """

    layout = "person_major"

    def read(self, grid, vocabulary) -> Scored:
        header = find_nested_header(grid, vocabulary)
        if header is None:
            return None
        shift_row, columns = header
        shifts = list(dict.fromkeys(shift for _column, _iso, shift in columns))
        data_columns = [column for column, _iso, _shift in columns]
        cells = CellCollector()
        for row in grid[shift_row + 1:MAX_ROWS]:
            lane = lane_label(row, data_columns) or lane_from_cells(row, data_columns)
            for column, iso, shift_name in columns:
                cells.take(_cell(row, column), iso, shift_name, owner=lane)
            cells.add_person(lane)
        if not cells.assignments and not cells.unavailability:
            return None
        dates = list(dict.fromkeys(iso for _column, iso, _shift in columns))
        notes = year_warnings(dates)
        if cells.orphans():
            notes.append(_ORPHANS_NOTE % cells.orphans())
        return self._result(cells, shifts, sorted(dates), notes)


class DateOnlyReader(LayoutReader):
    """Dates and the people under them, with no shift axis at all.

    Tried last, and it claims a sheet only when no row carries a lane label:
    a labelled file is one of the other two layouts. The shift is left
    **empty** rather than named -- inventing one would be exactly the
    hardcoding D9 forbids, and an empty name makes the confirm screen ask.
    """

    layout = "date_only"

    def read(self, grid, vocabulary) -> Scored:
        header = find_date_row(grid)
        if header is None:
            return None
        row_index, dates = header
        columns = [column for column, _iso in dates]
        cells = CellCollector()
        for row in grid[first_data_row(grid, row_index, dates):MAX_ROWS]:
            if lane_label(row, columns):
                return None
            for column, iso in dates:
                cells.take(_cell(row, column), iso, "")
        if not cells.assignments:
            return None
        iso_dates = [iso for _column, iso in dates]
        notes = year_warnings(iso_dates) + [
            "בקובץ אין שמות משמרות — כל השיבוצים יובאו ללא משמרת. "
            "בחר את המשמרת לפני האישור"
        ]
        return self._result(cells, [], iso_dates, notes)


READERS = (PersonMajorReader(), ShiftMajorReader(), DateOnlyReader())
