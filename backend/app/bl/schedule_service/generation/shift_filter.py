"""Which shift types a build covers: all of them, or the ones the manager chose.

"Build only the nights for this month" is a range build narrowed by shift
rather than by date. The chosen shifts are solved; every row on any other
shift stands as it is and counts, for rest and load, as fixed — the solver
already keeps a row whose slot it was not asked for (`shift_names`).
"""

from typing import List, Optional, Set

from app.bl.schedule_service.rows import iso, text
from app.common.errors import AgentError


def chosen_shifts(requested: Optional[List[str]], slots: List[dict]) -> List[str]:
    """The requested shift names, checked against the stored grid.

    Empty means every shift, the default. A name the grid does not carry is
    refused rather than dropped: building nothing while the manager believes
    the nights were built is the failure this guards against (D9 — the names
    come from setup, so an unknown one is a stale screen, not a guess to make).
    """
    wanted = []
    for name in requested or []:
        name = text(name)
        if name and name not in wanted:
            wanted.append(name)
    if not wanted:
        return []
    known = {text(slot.get("shift_name")) for slot in slots}
    missing = [name for name in wanted if name not in known]
    if missing:
        raise AgentError("המשמרת %s אינה קיימת בסידור הזה" % ", ".join(missing))
    return wanted


def dates_with(slots: List[dict], shifts: List[str]) -> Set[str]:
    """The dates of the grid on which a chosen shift runs (every date if none)."""
    return {
        iso(slot.get("slot_date")) for slot in slots
        if not shifts or text(slot.get("shift_name")) in shifts
    }


def covered(row: dict, shifts: List[str]) -> bool:
    """Whether a build over `shifts` rewrites this row's shift."""
    return not shifts or text(row.get("shift")) in shifts
