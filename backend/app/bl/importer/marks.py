"""Classifying what a cell says: an absence, a handover note, several names.

Kept apart from `cells.py`, which reads values (text, dates, weekdays,
hours): these decide what a value *means* for the person it belongs to.
"""

import re
from typing import Iterable, List

from app.bl.importer.cells import normalise

# Availability markers living in the assignment grid (Sample B). Matched as
# whole cell values after normalisation, never as substrings.
_UNAVAILABLE = (
    "לא זמין", "לא זמינה", "לא יכול", "לא יכולה", "חופש", "חופשה", "מחלה",
    "חולה", "גימל", "אילוץ", "בית", "בבית",
)

# Words a cell adds to a person's name that say *how* they work the shift,
# not who they are: "עיינה-חפיפה" is עיינה, on a handover shift. Kept as the
# row's note rather than read as part of a name nobody on the roster has.
_NOTE_WORDS = ("חפיפה", "חפיפות", "בחפיפה", "חניכה", "תצפית")


def is_unavailable(value: str, extra: Iterable[str] = ()) -> bool:
    """Whether a cell says somebody cannot work. `extra` is the sheet's own
    markers ("X", "חופ"ש") -- named by the layout, since in one file an "X"
    means away and in another it means on shift."""
    cleaned = normalise(value)
    markers = tuple(_UNAVAILABLE) + tuple(normalise(word) for word in extra if word)
    return any(cleaned == marker or cleaned.startswith(marker) for marker in markers)


def split_note(part: str):
    """`(name, note)`: a person's name with any handover word taken off."""
    words = re.split(r"[\s\-–—()]+", part or "")
    notes = [word for word in words if word in _NOTE_WORDS]
    name = " ".join(word for word in words if word and word not in _NOTE_WORDS)
    return name.strip(), " ".join(notes)


def split_names(value: str) -> List[str]:
    """One cell into the people it names.

    `export.py` writes several people into a cell newline-separated, and the
    manager's own files use commas or slashes. The unfilled marker it writes
    is not a person.
    """
    from app.bl.export import UNFILLED

    names = []
    for part in re.split(r"[\n,/;]+", value or ""):
        name = part.strip()
        if name and name != UNFILLED and not name.startswith("—"):
            names.append(name)
    return names
