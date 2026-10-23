"""Each source's fate on its own: fully honoured, or left out whole.

- every directive and request is validated on its own, and a source whose
  items all pass is kept;
- a source the model left `unresolved`, did not cover, or covered with an
  item that failed is *left out*, and none of its items are used.

The solver builds with what was kept, and every left-out source is listed
so the schedule can say plainly which sentences it was built without
(D34). `per_source` is the first half on its own, because a translation
that is kept for later builds (`bl/compiled_sources/`) is stored one source
at a time; `assemble` turns any set of outcomes back into what code builds
with.
"""

from typing import Any, Dict, List, Optional

from app.bl.schedule_requests import read_requests
from app.bl.scheduler.directives import translated_row
from app.bl.scheduler.slots import build_slots
from app.bl.shared import text

_NOT_COVERED = "לא תורגם"
_FAILED = "התרגום לא עבר את הבדיקה בקוד"
_MAX_TEXT = 200


def per_source(answer: Any, sources: List[dict], profile: dict,
               starts_on: str, ends_on: str) -> Optional[Dict[str, dict]]:
    """Every source's fate on its own: `{"items": [(kind, value), ...]}`
    when all its items pass, else `{"left": reason}` -- with `retry` when
    code left it out rather than the model's own judgement. None for an
    answer that is not one at all. `kind` is `unavailable`,
    `required_assignment` or `request`."""
    if not isinstance(answer, dict):
        return None
    by_id = {row["id"]: row for row in sources}
    reasons = _unresolved(answer.get("unresolved"), by_id)
    kept: Dict[str, list] = {}
    failed = set()
    for source_id, item in _items(answer, by_id, profile, starts_on, ends_on):
        if item is None:
            failed.add(source_id)
        else:
            kept.setdefault(source_id, []).append(item)
    outcomes = {}
    for source_id in by_id:
        if source_id in reasons:
            outcomes[source_id] = {"left": reasons[source_id]}
        elif source_id in failed or source_id not in kept:
            outcomes[source_id] = {
                "left": _FAILED if source_id in failed else _NOT_COVERED, "retry": True}
        else:
            outcomes[source_id] = {"items": kept[source_id]}
    return outcomes


def _items(answer: dict, by_id: Dict[str, dict], profile: dict, starts_on: str, ends_on: str):
    """`(source_id, item)` for every directive and request, item None when
    code refused it."""
    people = {
        text(row.get("name")): row for row in (profile or {}).get("employees") or []
        if isinstance(row, dict) and text(row.get("name"))
    }
    slots = {(row["shift_name"], row["slot_date"]) for row in build_slots(profile, starts_on, ends_on)}
    standing = {source_id for source_id, row in by_id.items() if row.get("persistent")}
    shifts = {text(row.get("name")) for row in (profile or {}).get("shifts") or []
              if isinstance(row, dict)}
    for row in _rows(answer.get("directives")):
        read = translated_row(row, set(by_id), people, slots, standing, shifts)
        yield (row.get("source_id"), None) if read is None else (read[0], (read[1], read[2]))
    for row in _rows(answer.get("requests")):
        valid, errors = read_requests([row], profile)
        if errors or not valid or valid[0]["source_id"] not in by_id:
            yield row.get("source_id"), None
        else:
            yield valid[0]["source_id"], ("request", valid[0])


def assemble(outcomes: Dict[str, dict], by_id: Dict[str, dict], usage: dict) -> dict:
    """What code builds with: the kept items, and every left-out source said."""
    availability, required, requests = [], [], []
    for outcome in outcomes.values():
        for kind, value in outcome.get("items") or []:
            {"unavailable": availability, "required_assignment": required,
             "request": requests}[kind].append(value)
    return {
        "availability": availability,
        "required_assignments": required,
        "requests": requests,
        "unresolved": [
            {"source_id": source_id, "kind": by_id[source_id]["kind"],
             "text": by_id[source_id]["text"][:_MAX_TEXT], "reason": outcome["left"]}
            for source_id, outcome in outcomes.items() if "left" in outcome
        ],
        "usage": usage,
    }


def _unresolved(rows: Any, by_id: Dict[str, dict]) -> Dict[str, str]:
    return {
        row["source_id"]: text(row.get("reason")) or _NOT_COVERED
        for row in _rows(rows) if row.get("source_id") in by_id
    }


def _rows(value: Any) -> List[dict]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


__all__ = ["assemble", "per_source"]
