"""Strict structured outputs: a caller's schema in the form strict mode takes.

Strict mode (`json_schema` with `strict: true`) makes the server decode
against the schema, so the reply cannot be anything but a valid answer. It
takes a narrower form of schema than the callers write: every object lists
`additionalProperties: false` and *every* property as required. An optional
property becomes a required one that may be `null`, and `drop_nulls` takes
those nulls back out of the reply, so callers see exactly the shape they
always did.

A schema with a free-form object (no `properties`, or extra keys allowed)
cannot be stated strictly without forbidding what it allows, so `to_strict`
returns None and the ladder starts at the ordinary schema rung instead.
"""

import copy
from typing import Any, Optional


def to_strict(schema: Optional[dict]) -> Optional[dict]:
    """The strict form of `schema`, or None when it has no strict form."""
    if not isinstance(schema, dict):
        return None
    converted = copy.deepcopy(schema)
    return converted if _convert(converted) else None


def _convert(node: Any) -> bool:
    if not isinstance(node, dict):
        return True
    for key in ("anyOf", "oneOf", "allOf"):
        if key in node and not all(_convert(item) for item in node[key]):
            return False
    if "items" in node and not _convert(node["items"]):
        return False
    for definitions in ("$defs", "definitions"):
        if not all(_convert(item) for item in (node.get(definitions) or {}).values()):
            return False
    if not _is_object(node):
        return True
    properties = node.get("properties")
    if not isinstance(properties, dict) or not properties \
            or node.get("additionalProperties") not in (None, False):
        return False
    required = set(node.get("required") or [])
    for name, child in properties.items():
        if not _convert(child):
            return False
        if name not in required:
            properties[name] = _nullable(child)
    node["required"] = list(properties)
    node["additionalProperties"] = False
    return True


def _is_object(node: dict) -> bool:
    kind = node.get("type")
    return kind == "object" or (isinstance(kind, list) and "object" in kind) \
        or ("properties" in node and "type" not in node)


def _nullable(node: dict) -> dict:
    kind = node.get("type")
    if isinstance(kind, str):
        widened = dict(node, type=[kind, "null"])
        if "enum" in widened:
            widened["enum"] = list(widened["enum"]) + [None]
        return widened
    if isinstance(kind, list):
        return node if "null" in kind else dict(node, type=kind + ["null"])
    return {"anyOf": [node, {"type": "null"}]}


def drop_nulls(value: Any, schema: Optional[dict]) -> Any:
    """`value` with the nulls strict mode put in place of omitted optional
    properties removed, following the caller's original `schema`."""
    if not isinstance(schema, dict):
        return value
    if isinstance(value, list):
        return [drop_nulls(item, schema.get("items")) for item in value]
    if not isinstance(value, dict) or not isinstance(schema.get("properties"), dict):
        return value
    required = set(schema.get("required") or [])
    properties = schema["properties"]
    return {
        key: drop_nulls(item, properties.get(key))
        for key, item in value.items()
        if not (item is None and key in properties and key not in required)
    }


__all__ = ["drop_nulls", "to_strict"]
