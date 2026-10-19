"""`read_partial`: keep what translated, when what did not is only a wish.

`read_translation` is all or nothing, and it is right to be for anything
binding: a "must" code cannot honour has to reach the full scheduler. But
one vague wish ("עדיף לשאול את יוסי לפני רון") used to send the whole
period there too. Here a source is either fully honoured or reported:

- every directive and request is validated on its own, and a source whose
  items all pass is kept;
- a source the model left `unresolved`, did not cover, or covered with an
  item that failed is *left out*, and none of its items are used;
- if any left-out source is binding, there is no partial answer (None);
  otherwise the rest is returned with the left-out sources listed, so the
  schedule can say plainly which wishes it was built without.
"""

from typing import Any, Dict, List, Optional

from app.bl.schedule_requests import read_requests
from app.bl.scheduler.directives import translated_row
from app.bl.scheduler.slots import build_slots
from app.bl.scheduler.span_audit import usage_of
from app.bl.shared import text

_NOT_COVERED = "לא תורגם"
_FAILED = "התרגום לא עבר את הבדיקה בקוד"
_MAX_TEXT = 200


def read_partial(answer: Any, sources: List[dict], profile: dict,
                 starts_on: str, ends_on: str) -> Optional[dict]:
    if not isinstance(answer, dict):
        return None
    by_id = {row["id"]: row for row in sources}
    reasons = _unresolved(answer.get("unresolved"), by_id)
    kept: Dict[str, list] = {}
    failed = set()
    people = {
        text(row.get("name")): row for row in (profile or {}).get("employees") or []
        if isinstance(row, dict) and text(row.get("name"))
    }
    slots = {(row["shift_name"], row["slot_date"]) for row in build_slots(profile, starts_on, ends_on)}
    for row in _rows(answer.get("directives")):
        read = translated_row(row, set(by_id), people, slots)
        if read is None:
            failed.add(row.get("source_id"))
        else:
            kept.setdefault(read[0], []).append((read[1], read[2]))
    for row in _rows(answer.get("requests")):
        valid, errors = read_requests([row], profile)
        if errors or not valid or valid[0]["source_id"] not in by_id:
            failed.add(row.get("source_id"))
        else:
            kept.setdefault(valid[0]["source_id"], []).append(("request", valid[0]))
    left = {
        source_id: reasons.get(source_id) or (_FAILED if source_id in failed else _NOT_COVERED)
        for source_id in by_id
        if source_id in reasons or source_id in failed or source_id not in kept
    }
    if any(by_id[source_id].get("binding", True) for source_id in left):
        return None
    return _result(kept, left, by_id, answer)


def _result(kept: Dict[str, list], left: Dict[str, str], by_id: Dict[str, dict],
            answer: dict) -> dict:
    availability, required, requests = [], [], []
    for source_id, items in kept.items():
        if source_id in left:
            continue
        for kind, value in items:
            {"unavailable": availability, "required_assignment": required,
             "request": requests}[kind].append(value)
    return {
        "availability": availability,
        "required_assignments": required,
        "requests": requests,
        "unresolved": [
            {"source_id": source_id, "kind": by_id[source_id]["kind"],
             "text": by_id[source_id]["text"][:_MAX_TEXT], "reason": reason}
            for source_id, reason in left.items()
        ],
        "usage": usage_of(answer),
    }


def _unresolved(rows: Any, by_id: Dict[str, dict]) -> Dict[str, str]:
    return {
        row["source_id"]: text(row.get("reason")) or _NOT_COVERED
        for row in _rows(rows) if row.get("source_id") in by_id
    }


def _rows(value: Any) -> List[dict]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


__all__ = ["read_partial"]
