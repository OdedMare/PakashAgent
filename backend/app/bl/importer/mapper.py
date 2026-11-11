"""`LayoutMapper`: asking the model what a sheet's axes mean.

The model is shown the sheet's corner, the roster and the shift names, and
answers with a `Layout` -- which line carries the dates, what a lane is --
and nothing else. It never names who works when: code reads every cell
with the layout it returns and scores the result against the roster
exactly as it scores its own guesses (`detect.evaluate`), so a layout the
model got wrong loses to a better one rather than reaching the screen.
"""

import json
from typing import List, Optional

from app.bl.importer.cells import text
from app.bl.importer.layout import LANES, ORIENTATIONS
from app.bl.prompts import load
from app.bl.tools.values import employees
from app.common.errors import AgentError

_SAMPLE_ROWS = 30
_SAMPLE_COLUMNS = 24
_CELL_CHARACTERS = 24
_ROSTER_NAMES = 120
_HINT_CHARACTERS = 500

_INDEX = {"type": "integer"}
_WORDS = {"type": "array", "items": {"type": "string"}}

LAYOUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["orientation", "header", "lanes", "explanation"],
    "properties": {
        "orientation": {"type": "string", "enum": list(ORIENTATIONS)},
        "header": {"type": "integer"},
        "shift_line": _INDEX,
        "label": _INDEX,
        "lanes": {"type": "string", "enum": list(LANES)},
        "first_line": _INDEX,
        "last_line": _INDEX,
        "unavailable": _WORDS,
        "ignore": _WORDS,
        "explanation": {"type": "string"},
    },
}


class LayoutMapper(object):
    def __init__(self, llm):
        self._llm = llm

    def propose(self, grid: List[List[str]], profile: Optional[dict],
                hint: str = "", previous: Optional[dict] = None) -> Optional[dict]:
        """A layout dict with its `explanation`, or None when the model could
        not be asked or did not answer with one. Never raises: the importer
        still has its own guesses to show."""
        if self._llm is None or not grid:
            return None
        payload = _payload(grid, profile, hint, previous)
        try:
            answer = self._llm.complete_json(
                load("import_layout"), json.dumps(payload, ensure_ascii=False),
                schema=LAYOUT_SCHEMA, flow="import",
            )
        except AgentError:
            return None
        if not isinstance(answer, dict) or answer.get("orientation") not in ORIENTATIONS:
            return None
        answer.pop("_usage", None)
        return answer


def _payload(grid, profile: Optional[dict], hint: str, previous: Optional[dict]) -> dict:
    payload = {
        "sheet": _sample(grid),
        "size": {"rows": len(grid), "columns": max((len(row) for row in grid), default=0)},
        "roster": [text(row.get("name")) for row in employees(profile or {})
                   if text(row.get("name"))][:_ROSTER_NAMES],
        "shifts": [
            {"name": text(shift.get("name")),
             "hours": "%s-%s" % (text(shift.get("start_time")), text(shift.get("end_time")))}
            for shift in (profile or {}).get("shifts") or [] if isinstance(shift, dict)
        ],
    }
    if text(hint):
        payload["hint"] = text(hint)[:_HINT_CHARACTERS]
    if previous:
        payload["previous"] = previous
    return payload


def _sample(grid: List[List[str]]) -> List[dict]:
    """The sheet's corner, empty trailing cells and rows dropped."""
    rows = []
    for index, row in enumerate(grid[:_SAMPLE_ROWS]):
        cells = [text(value)[:_CELL_CHARACTERS] for value in row[:_SAMPLE_COLUMNS]]
        while cells and not cells[-1]:
            cells.pop()
        if cells:
            rows.append({"row": index, "cells": cells})
    return rows
