"""`infer()`: one sheet, its layout found, read and interpreted.

Three sources answer "how is this sheet laid out", in this order, and every
answer is read and scored by the same code:

1. **The manager**, when the confirm screen sends a layout back. It is read
   as given -- the manager has looked at the sheet -- and scored only so
   the screen can say how well it fits.
2. **Detection** (`detect.py`), which reads the sheet every plausible way.
3. **The model** (`mapper.py`), asked only when detection is unsure, finds
   nothing, or the manager described the file in words. Its layout must
   out-score detection's best to be used.

The two best distinct readings travel with the answer as alternatives, so
a wrong guess is one click from the right one rather than a form to fill.
"""

from typing import Dict, List, Optional

from app.bl.importer.detect import detect, evaluate
from app.bl.importer.files import bounded
from app.bl.importer.interpretation import describe, interpret
from app.bl.importer.layout import Layout
from app.bl.importer.reader import read
from app.bl.importer.vocabulary import ShiftVocabulary
from app.common.errors import AgentError

SOURCE_MANAGER = "manager"
SOURCE_DETECTED = "detected"
SOURCE_MODEL = "model"

# Below this, detection's best guess is checked with the model.
_CONFIDENT = 0.75
_ALTERNATIVES = 3
_PREVIEW_ROWS = 40
_PREVIEW_COLUMNS = 26


def infer(grid: List[List[str]], profile: Optional[dict] = None,
          layout: Optional[dict] = None, mapper=None, week_start: str = "",
          hint: str = "", names: Optional[Dict[str, str]] = None,
          shifts: Optional[Dict[str, str]] = None, date_from: str = "",
          date_to: str = "") -> dict:
    """The interpretation the confirm screen shows. Raises `AgentError` in
    Hebrew when no layout explains the sheet at all."""
    grid = bounded(grid)
    if not grid or not any(any(cell for cell in row) for row in grid):
        raise AgentError("הגיליון ריק")
    vocabulary = ShiftVocabulary.from_profile(profile)
    if layout:
        chosen = _manager(grid, profile, vocabulary, layout, week_start)
        alternatives = []
    else:
        ranked = detect(grid, profile, vocabulary, week_start)
        chosen = _best(grid, profile, vocabulary, ranked, mapper, hint, week_start)
        alternatives = _alternatives(ranked, chosen)
    reading = chosen["reading"]
    result = interpret(reading, profile, vocabulary, names, shifts, (date_from, date_to))
    result.update(
        layout=reading.layout.to_dict(),
        layout_source=chosen["source"],
        explanation=chosen.get("explanation") or describe(reading.layout),
        confidence=chosen["confidence"],
        alternatives=alternatives,
        sheet=preview(grid),
    )
    if chosen["confidence"] < 0.5:
        result["warnings"].insert(0, "לא בטוח שהמבנה זוהה נכון — בדוק את התצוגה או תקן את הפריסה")
    return result


def preview(grid: List[List[str]]) -> List[List[str]]:
    """The sheet's corner as the screen draws it, beside the reading."""
    rows = [row[:_PREVIEW_COLUMNS] for row in grid[:_PREVIEW_ROWS]]
    while rows and not any(rows[-1]):
        rows.pop()
    return rows


def _manager(grid, profile, vocabulary, layout: dict, week_start: str) -> dict:
    reading = read(grid, Layout.from_dict(layout), vocabulary, week_start)
    _score, confidence = evaluate(reading, profile, vocabulary)
    return {"reading": reading, "source": SOURCE_MANAGER, "confidence": confidence}


def _best(grid, profile, vocabulary, ranked, mapper, hint: str, week_start: str) -> dict:
    best = None
    if ranked:
        score, confidence, reading = ranked[0]
        best = {"reading": reading, "source": SOURCE_DETECTED,
                "confidence": confidence, "score": score}
    if mapper is not None and (best is None or best["confidence"] < _CONFIDENT or hint):
        modelled = _modelled(grid, profile, vocabulary, mapper, hint, week_start, best)
        if modelled is not None and (best is None or modelled["score"] >= best["score"]):
            best = modelled
    if best is None:
        raise AgentError(
            "לא הצלחתי לזהות את מבנה הקובץ. ודא שיש בו שורה או עמודה של תאריכים "
            "או ימים בשבוע, או תאר את הקובץ במילים ונסה שוב"
        )
    return best


def _modelled(grid, profile, vocabulary, mapper, hint, week_start, best) -> Optional[dict]:
    previous = None
    if best is not None:
        previous = {"layout": best["reading"].layout.to_dict(),
                    "confidence": best["confidence"],
                    "rows_read": len(best["reading"].assignments)}
    answer = mapper.propose(grid, profile, hint=hint, previous=previous)
    if not answer:
        return None
    try:
        reading = read(grid, Layout.from_dict(answer), vocabulary, week_start)
    except AgentError:
        return None
    score, confidence = evaluate(reading, profile, vocabulary)
    if score <= 0:
        return None
    return {"reading": reading, "source": SOURCE_MODEL, "confidence": confidence,
            "score": score, "explanation": str(answer.get("explanation") or "")[:300]}


def _alternatives(ranked, chosen: dict) -> List[dict]:
    """Other readings that differ in what they store, best first."""
    taken = {_fingerprint(chosen["reading"])}
    found = []
    for _score, confidence, reading in ranked:
        print_ = _fingerprint(reading)
        if print_ in taken or not reading.assignments:
            continue
        taken.add(print_)
        found.append({"layout": reading.layout.to_dict(), "confidence": confidence,
                      "explanation": describe(reading.layout),
                      "rows": len(reading.assignments)})
        if len(found) >= _ALTERNATIVES:
            break
    return found


def _fingerprint(reading) -> frozenset:
    return frozenset((row["employee"], row["shift"], row["date"])
                     for row in reading.assignments)
