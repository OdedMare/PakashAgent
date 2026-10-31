"""Absorbing a change into a board that already exists: move as few people
as the change needs.

A rebuild handed `keep` rows (the board as it stood) rewards every one of
them still standing where it was. The reward is priced against the
evenness terms (`fairness.py`) on purpose. Handing one shift from somebody
above their target to somebody below it — a newcomer, say — gains twice
what keeping it is worth, so it happens; handing it from somebody already
at their target gains nothing and costs the keep, so it does not. A new
soldier therefore takes shifts only from whoever carries more than their
share, and only until the load is even; a new shift is filled without
reshuffling the rows around it unless coverage demands it. Coverage is
still settled first (`solve._phases`), so a kept row never holds a seat
empty.
"""

from typing import List

from app.bl.solver.model import NIGHT_SCALE, NIGHT_SPREAD, SHIFT_SCALE, SHIFT_SPREAD, Model

_KEPT = "שובץ/ה כבר בסידור הקיים; השיבוץ נשמר."
_ABSORBED = "השינוי הוטמע בסידור הקיים: %d שיבוצים נשמרו, %d הוזזו או התפנו."


def apply_stability(model: Model) -> None:
    problem = model.problem
    for key in sorted(problem.keep):
        var = model.x.get(key)
        if var is not None:
            model.price(-_worth(problem, key[1]), var, kind="keep")


def _worth(problem, index: int) -> int:
    """Half of what moving this shift from an overloaded person to an
    underloaded one gains in evenness (a shift, and a night for a night)."""
    worth = SHIFT_SCALE * SHIFT_SPREAD
    if problem.times[index]["night"]:
        worth += NIGHT_SCALE * NIGHT_SPREAD
    return worth


def kept_reason(problem, name: str, index: int) -> str:
    """The reason the row already carried, or a plain statement it stayed."""
    return problem.keep.get((name, index)) or _KEPT


def absorbed(problem, chosen: List[dict]) -> dict:
    """How many of the board's rows stayed and how many moved."""
    placed = {(row["employee"], problem.keys.get((row["shift"], row["date"]))) for row in chosen}
    stayed = sum(1 for key in problem.keep if key in placed)
    return {"kept": stayed, "moved": problem.kept_rows - stayed}


def absorbed_note(counts: dict) -> str:
    return _ABSORBED % (counts["kept"], counts["moved"])
