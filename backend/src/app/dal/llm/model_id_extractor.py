"""Pull model IDs out of a `/models` response.

Compatible servers disagree on the envelope (`data`, `models`, or a bare
list) and on the id field (`id`, `name`, `model`), so all are accepted.
"""

from typing import List


def extract_model_ids(payload) -> List[str]:
    items = payload
    if isinstance(payload, dict):
        items = payload.get("data", payload.get("models", []))
    if not isinstance(items, list):
        return []
    identifiers = set()
    for item in items:
        if isinstance(item, str):
            identifiers.add(item)
        elif isinstance(item, dict):
            value = item.get("id") or item.get("name") or item.get("model")
            if value:
                identifiers.add(str(value))
    return sorted(identifiers)
