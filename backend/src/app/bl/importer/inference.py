"""`infer()`: read a grid as a schedule, inferring what its axes mean."""

from typing import List, Optional

from app.bl.importer.cells import is_yearless
from app.bl.importer.files import bounded
from app.bl.importer.headers import MAX_HEADER_SCAN
from app.bl.importer.interpretation import Interpretation
from app.bl.importer.layouts import READERS
from app.bl.importer.vocabulary import ShiftVocabulary
from app.common.errors.errors import AgentError

# How close a runner-up layout's score must be to call the sheet ambiguous.
_AMBIGUITY_RATIO = 0.85


def infer(grid: List[List[str]], profile: Optional[dict] = None) -> Interpretation:
    """Read a grid as a schedule, inferring what its axes mean.

    Tries every layout and keeps whichever explains more of the sheet --
    scoring them against each other is more honest than a heuristic that
    picks first and hopes.
    """
    grid = bounded(grid)
    if not grid:
        raise AgentError("הקובץ ריק או לא נקרא")
    candidates = _candidates(grid, ShiftVocabulary.from_profile(profile))
    if not candidates:
        raise AgentError(
            "לא הצלחתי לזהות את מבנה הקובץ. "
            "ודא שיש בו שורת תאריכים ושמות משמרות"
        )
    ranked = _ranked(candidates)
    best_score, result = ranked[0]
    if (
        len(ranked) > 1
        and ranked[1][1].layout != result.layout
        and ranked[1][0] >= best_score * _AMBIGUITY_RATIO
    ):
        result.warnings.append(
            "המבנה אינו חד־משמעי; בדוק שהשורות והעמודות "
            "פורשו נכון לפני האישור"
        )
    if _has_yearless_dates(grid):
        result.warnings.append(
            "בקובץ יש תאריכים ללא שנה; השנה הנוכחית הונחה — "
            "ודא אותה לפני האישור"
        )
    return result.deduplicate()


def _candidates(grid: List[List[str]], vocabulary: ShiftVocabulary) -> list:
    found = []
    for reader in READERS:
        try:
            scored = reader.read(grid, vocabulary)
        except AgentError:
            scored = None
        if scored is not None:
            found.append(scored)
    return found


def _ranked(candidates: list) -> list:
    """More explained cells wins, but a real shift axis always beats none.

    `date_only` explains every filled cell by construction, so scoring it
    against the others would let it win whenever it applies and flatten a
    shift axis that was really there. It is a fallback, and fallbacks go last.
    """
    structured = [found for found in candidates if found[1].layout != "date_only"]
    return sorted(structured or candidates, key=lambda found: found[0], reverse=True)


def _has_yearless_dates(grid: List[List[str]]) -> bool:
    return any(
        is_yearless(value)
        for row in grid[:MAX_HEADER_SCAN] for value in row
    )
