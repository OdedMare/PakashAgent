"""A source's outcome as a stored row, and a stored row back as an outcome.

An outcome is what `directive_agent.partial.per_source` gives one source:
`{"items": [(kind, value), ...]}` or `{"left": reason}`. A stored row keeps
the items under `translation` without the positional `source_id` the model
worked with, since the next build numbers its sources afresh.

A row read back is checked again against today's roster and vocabulary
before it is used; one that no longer passes is not an outcome at all, and
the source is translated again.
"""

from typing import Optional

from app.bl.schedule_requests import read_requests
from app.bl.shared import text

STATUS_COMPILED = "compiled"
STATUS_UNRESOLVED = "unresolved"
_LISTS = (("unavailable", "availability"), ("required_assignment", "required_assignments"),
          ("request", "requests"))


def to_row(source: dict, outcome: dict, tokens: int, anchored_on: str) -> dict:
    translation = {name: [] for _, name in _LISTS}
    names = dict(_LISTS)
    for kind, value in outcome.get("items") or []:
        translation[names[kind]].append({key: item for key, item in value.items() if key != "source_id"})
    return {
        "source_key": source["key"], "kind": source["kind"], "context": source["context"],
        "text": source["text"], "binding": bool(source.get("binding", True)),
        "status": STATUS_UNRESOLVED if "left" in outcome else STATUS_COMPILED,
        "translation": translation, "reason": outcome.get("left") or "",
        "expires_on": outcome.get("expires_on") or None,
        "question": outcome.get("question") or "", "tokens": int(tokens),
        "anchored_on": anchored_on or None,
    }


def to_outcome(row: dict, source: dict, profile: dict) -> Optional[dict]:
    if row.get("status") == STATUS_UNRESOLVED:
        return {"left": row.get("reason") or "", "cached": True}
    translation = row.get("translation") or {}
    people = {text(item.get("name")) for item in (profile or {}).get("employees") or []
              if isinstance(item, dict)}
    shifts = {text(item.get("name")) for item in (profile or {}).get("shifts") or []
              if isinstance(item, dict)}
    items = []
    for kind, name in _LISTS[:2]:
        for value in translation.get(name) or []:
            if text(value.get("employee")) not in people or text(value.get("shift")) not in shifts:
                return None
            items.append((kind, dict(value)))
    raw = [dict(value, source_id=source["id"]) for value in translation.get("requests") or []]
    requests, errors = read_requests(raw, profile)
    if errors:
        return None
    items.extend(("request", value) for value in requests)
    return {"items": items, "cached": True}


__all__ = ["STATUS_COMPILED", "STATUS_UNRESOLVED", "to_outcome", "to_row"]
