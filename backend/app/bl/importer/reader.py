"""`read()`: one sheet read against one `Layout`.

The single reader every layout goes through. What a cell means follows
from the layout, not from a class per shape:

| Lanes | Shift line | A cell holds |
|---|---|---|
| `shifts` | — | the people on that shift that date (Sample A) |
| `people` | — | the shift the lane's person works that date |
| `people` | yes | a mark that the lane's person works that shift (Sample B) |
| `none` | yes | the people on the column's shift |
| `none` | — | the people working that date, no shift at all |

Availability lives in the same grid, so every cell is classified rather
than read: a marker becomes an absence, an ignored value nothing, anything
else a placement. A block of dates repeated further down -- a month kept as
weeks stacked on one sheet -- restarts the dates where it appears.
"""

from typing import List, Optional, Tuple

from app.bl.export import UNFILLED
from app.bl.importer.cells import is_yearless, normalise, text
from app.bl.importer.marks import is_unavailable, split_names, split_note
from app.bl.importer.headers import (
    carried, header_dates, is_date_row, is_title, is_weekday_row, lane_from_cells,
    lane_label, line_dates,
)
from app.bl.importer.layout import LANES_NONE, LANES_PEOPLE, LANES_SHIFTS, Layout, orient
from app.bl.importer.vocabulary import ShiftVocabulary
from app.common.errors import AgentError

_ALWAYS_IGNORED = (UNFILLED, "-", "–", "—", "--", "0", "?")
# A cross in a person's lane where a shift name belongs: that day they are
# out. Only there -- in a lane of shifts, a cross under a nested header can
# just as well mean "on shift", and the layout's own markers decide.
_CROSSES = ("x", "X", "✗", "✘", "×")

# (column, date, shift) for every data column.
Columns = List[Tuple[int, str, str]]


class Reading(object):
    """What one layout made of one sheet, before anybody approves it."""

    def __init__(self, layout: Layout):
        self.layout = layout
        self.assignments: List[dict] = []
        self.unavailability: List[dict] = []
        self.labels: List[str] = []
        self.notes: List[str] = []
        self.filled = 0
        self.explained = 0
        self.assumed_week = ""
        self.yearless = False

    def dates(self) -> List[str]:
        return sorted({row["date"] for row in self.assignments + self.unavailability})

    def shifts(self) -> List[str]:
        found = [row["shift"] for row in self.assignments + self.unavailability]
        return list(dict.fromkeys(name for name in found if name))


def read(grid: List[List[str]], layout: Layout, vocabulary: ShiftVocabulary,
         week_start: str = "") -> Reading:
    """Read `grid` as `layout` says. Raises `AgentError` when the layout
    does not fit the sheet at all -- the header line holds no dates."""
    oriented = orient(grid, layout.orientation)
    if layout.header >= len(oriented):
        raise AgentError("שורת הכותרת שנבחרה מחוץ לטבלה")
    reading = Reading(layout)
    columns = _columns(oriented, layout, vocabulary, week_start, reading)
    if not columns:
        raise AgentError("בשורה שנבחרה ככותרת אין תאריכים או ימים בשבוע")
    _Lanes(oriented, layout, vocabulary, reading).walk(columns)
    return reading


def _columns(grid, layout: Layout, vocabulary, week_start: str, reading: Reading) -> Columns:
    dates, assumed = header_dates(grid[layout.header], week_start)
    reading.assumed_week = assumed
    if any(is_yearless(value) for value in grid[layout.header]):
        reading.yearless = True
        reading.notes.append("בקובץ יש תאריכים ללא שנה; הונחה השנה הקרובה להיום — "
                             "אפשר לבחור את השנה")
    if not dates:
        return []
    if not layout.nested:
        return [(column, iso, "") for column, iso in dates]
    if layout.shift_line >= len(grid):
        return []
    return _nested(grid[layout.shift_line], dates, vocabulary)


def _nested(shift_row: List[str], dates, vocabulary: ShiftVocabulary) -> Columns:
    """Shift names under carried dates: `date x shift` columns."""
    by_column = carried(dates, len(shift_row))
    columns = []
    for column, value in enumerate(shift_row):
        shift = vocabulary.match(value)
        if shift and column in by_column:
            columns.append((column, by_column[column], shift))
    return columns


class _Lanes(object):
    """Walks the data lines, classifying each filled cell exactly once."""

    def __init__(self, grid, layout: Layout, vocabulary: ShiftVocabulary, reading: Reading):
        self._grid = grid
        self._layout = layout
        self._vocabulary = vocabulary
        self._reading = reading
        self._ignored = {normalise(word) for word in _ALWAYS_IGNORED + tuple(layout.ignore)}

    def walk(self, columns: Columns) -> None:
        last = self._layout.last_line
        end = len(self._grid) if last is None else min(len(self._grid), last + 1)
        for index in range(self._layout.data_start(), end):
            row = self._grid[index]
            data = [column for column, _date, _shift in columns]
            if not any(text(value) for value in row):
                continue
            restarted = self._restart(row, columns, index)
            if restarted is not None:
                columns = restarted
                continue
            if is_weekday_row(row, data) or self._shift_row(row, columns):
                continue
            self._lane(row, columns)

    def _restart(self, row, columns: Columns, index: int) -> Optional[Columns]:
        """New dates for the same columns when the header repeats."""
        data = [column for column, _date, _shift in columns]
        if not is_date_row(row, data):
            return None
        dates = dict(line_dates(row))
        if self._layout.nested:
            spread = carried(sorted(dates.items()), len(row))
            return [(column, spread.get(column, date), shift)
                    for column, date, shift in columns]
        return [(column, dates.get(column, date), shift) for column, date, shift in columns]

    def _shift_row(self, row, columns: Columns) -> bool:
        """A repeated shift line under a repeated date line (nested blocks)."""
        if not self._layout.nested:
            return False
        return self._vocabulary.mostly_shifts(row, [(c, d) for c, d, _s in columns])

    def _lane(self, row: List[str], columns: Columns) -> None:
        data = [column for column, _date, _shift in columns]
        lanes, label = self._layout.lanes, lane_label(row, data, self._layout.label)
        # A caption, or a legend row labelled with a marker ("בית"), is not
        # anybody's lane.
        if label and (is_title(label) or is_unavailable(label, self._layout.unavailable)):
            return
        if lanes == LANES_SHIFTS:
            shift = self._vocabulary.match(label) if label else ""
            if not shift and not self._layout.nested:
                return
            self._names(row, columns, shift)
        elif lanes == LANES_PEOPLE:
            owner = label or lane_from_cells(row, data, self._layout.unavailable)
            if owner:
                self._reading.labels.append(owner)
            self._person(row, columns, owner)
        elif lanes == LANES_NONE:
            self._names(row, columns, "")

    def _names(self, row, columns: Columns, lane_shift: str) -> None:
        """Cells naming people, on the column's shift or the lane's."""
        for column, date, shift in columns:
            for part in self._parts(row, column):
                if is_unavailable(part, self._layout.unavailable):
                    self._absent("", date, shift or lane_shift, part)
                else:
                    name, note = split_note(part)
                    self._place(name, date, shift or lane_shift, note)

    def _person(self, row, columns: Columns, owner: str) -> None:
        """One person's lane: a cell says what they work, or only that they do."""
        for column, date, shift in columns:
            # What a person's cell says is one thing -- "צמא (משמרת בוקר)",
            # "בהצלחה, אין עליכם!" -- so only a new line splits it.
            for part in self._parts(row, column, whole=True):
                if is_unavailable(part, self._layout.unavailable):
                    self._absent(owner, date, shift, part)
                elif shift:
                    self._place(owner, date, shift, split_note(part)[1])
                elif part.strip() in _CROSSES and not self._vocabulary.declared(part):
                    self._absent(owner, date, "", part)
                else:
                    self._place(owner, date, self._vocabulary.match(part) or part)

    def _parts(self, row, column: int, whole: bool = False) -> List[str]:
        value = row[column] if column < len(row) else ""
        if not text(value):
            return []
        self._reading.filled += 1
        found = [line.strip() for line in text(value).split("\n")] if whole else split_names(value)
        parts = [part for part in found if part and normalise(part) not in self._ignored]
        if parts or normalise(value) in self._ignored:
            self._reading.explained += 1
        return parts

    def _place(self, employee: str, date: str, shift: str, note: str = "") -> None:
        if employee:
            row = {"employee": employee, "shift": shift, "date": date}
            if note:
                row["reason"] = note
            self._reading.assignments.append(row)

    def _absent(self, employee: str, date: str, shift: str, reason: str) -> None:
        self._reading.unavailability.append(
            {"employee": employee, "shift": shift, "date": date, "reason": reason})

