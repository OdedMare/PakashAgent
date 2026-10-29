"""`Layout`: what a sheet's axes mean, as data rather than as a reader class.

The importer used to hold one class per layout it had seen, and every file
that predated the app in a new shape needed another. Here the shape is a
small description -- which way time runs, which line carries the dates,
whether a shift line sits under them, what a lane is -- and one reader
(`reader.py`) reads any sheet given one. Detection, the model and the
manager all answer the same question in the same form, so a layout the
manager corrects on the confirm screen is read by exactly the code that
read the guess.

Indices are zero-based and refer to the sheet **as it is oriented after
`orientation` is applied**: with `dates_down` the grid is transposed first,
so `header` is then a column of the original file and `label` a row. The
screen shows the manager one-based row and column numbers of the original.
"""

from typing import List, Optional

DATES_ACROSS = "dates_across"
DATES_DOWN = "dates_down"
ORIENTATIONS = (DATES_ACROSS, DATES_DOWN)

# What one lane (a line parallel to the header's crossing axis) stands for.
LANES_SHIFTS = "shifts"      # a lane per shift, cells name people (Sample A)
LANES_PEOPLE = "people"      # a lane per person, cells say what they work
LANES_NONE = "none"          # lanes are only positions; cells name people
LANES = (LANES_SHIFTS, LANES_PEOPLE, LANES_NONE)

_MAX_MARKERS = 20
_MAX_MARKER_LENGTH = 30


class Layout(object):
    def __init__(
        self,
        orientation: str = DATES_ACROSS,
        header: int = 0,
        shift_line: Optional[int] = None,
        label: Optional[int] = None,
        lanes: str = LANES_SHIFTS,
        first_line: Optional[int] = None,
        last_line: Optional[int] = None,
        unavailable: Optional[List[str]] = None,
        ignore: Optional[List[str]] = None,
    ):
        self.orientation = orientation if orientation in ORIENTATIONS else DATES_ACROSS
        self.header = max(0, int(header or 0))
        self.shift_line = _index(shift_line)
        self.label = _index(label)
        self.lanes = lanes if lanes in LANES else LANES_SHIFTS
        self.first_line = _index(first_line)
        self.last_line = _index(last_line)
        self.unavailable = _words(unavailable)
        self.ignore = _words(ignore)

    @property
    def nested(self) -> bool:
        return self.shift_line is not None

    def data_start(self) -> int:
        """The first line holding data: after the header and any shift line."""
        if self.first_line is not None:
            return self.first_line
        return max(self.header, self.shift_line or 0) + 1

    def to_dict(self) -> dict:
        return {
            "orientation": self.orientation,
            "header": self.header,
            "shift_line": self.shift_line,
            "label": self.label,
            "lanes": self.lanes,
            "first_line": self.first_line,
            "last_line": self.last_line,
            "unavailable": list(self.unavailable),
            "ignore": list(self.ignore),
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "Layout":
        """A layout from the screen or the model. Never raises: an unknown
        value falls back to the default rather than refusing the read, and
        the score then says whether it explains the sheet."""
        data = data if isinstance(data, dict) else {}
        try:
            header = int(data.get("header") or 0)
        except (TypeError, ValueError):
            header = 0
        return cls(
            orientation=str(data.get("orientation") or DATES_ACROSS),
            header=header,
            shift_line=data.get("shift_line"),
            label=data.get("label"),
            lanes=str(data.get("lanes") or LANES_SHIFTS),
            first_line=data.get("first_line"),
            last_line=data.get("last_line"),
            unavailable=data.get("unavailable"),
            ignore=data.get("ignore"),
        )

    def key(self) -> tuple:
        return tuple(sorted(
            (name, tuple(value) if isinstance(value, list) else value)
            for name, value in self.to_dict().items()
        ))


def orient(grid: List[List[str]], orientation: str) -> List[List[str]]:
    """The grid with dates running across the top."""
    if orientation != DATES_DOWN or not grid:
        return grid
    width = max(len(row) for row in grid)
    return [
        [row[column] if column < len(row) else "" for row in grid]
        for column in range(width)
    ]


def _index(value) -> Optional[int]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _words(values) -> List[str]:
    if not isinstance(values, list):
        return []
    found = []
    for value in values[:_MAX_MARKERS]:
        word = str(value or "").strip()[:_MAX_MARKER_LENGTH]
        if word and word not in found:
            found.append(word)
    return found
