"""The shape of one interview turn the model must return."""

import copy

from app.bl.interview.profile_schema import OBJECT_FIELDS, PROFILE_SCHEMA
from app.bl.interview.topics import (
    CONTINUE_TOPIC_ID, CORE_TOPIC_IDS, OPTIONAL_TOPIC_ID,
)

# Clickable answers per question. Past four the manager is reading a list
# instead of choosing, which is the deliberation the options exist to save.
MAX_OPTIONS = 4

_OPTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["label", "answer"],
    "properties": {
        # The button caption.
        "label": {"type": "string"},
        # The full sentence sent as the manager's own message when clicked.
        # An option without one has nothing to send, so both are required.
        "answer": {"type": "string"},
    },
}

_QUESTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topic_id", "question", "recommendation", "why", "options"],
    "properties": {
        "topic_id": {
            "type": "string",
            "enum": list(CORE_TOPIC_IDS) + [CONTINUE_TOPIC_ID, OPTIONAL_TOPIC_ID],
        },
        "question": {"type": "string"},
        "recommendation": {"type": "string"},
        "why": {"type": "string"},
        "options": {
            "type": "array", "items": _OPTION_SCHEMA,
            "minItems": 2, "maxItems": MAX_OPTIONS,
        },
    },
}


def _draft_update_schema() -> dict:
    """A sparse profile: omitted fields keep their previous value.

    Employee and shift items are partial too: the manager commonly gives the
    names before roles, hours, or eligibility. Requiring every later detail
    on that first turn makes the model claim it recorded the list while being
    unable to put it in ``draft_update`` without guessing.
    """
    schema = copy.deepcopy(PROFILE_SCHEMA)
    schema.pop("required", None)
    for field in OBJECT_FIELDS:
        schema["properties"][field].pop("required", None)
    for field in ("employees", "shifts"):
        schema["properties"][field]["items"].pop("required", None)
    return schema


INTERVIEW_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "reply", "question", "resolved", "open_points",
        "awaiting_confirmation", "ready", "draft_update",
    ],
    "properties": {
        "reply": {"type": "string"},
        # Null on the turn that presents the summary and on the turn that
        # finishes; a question object on every other turn.
        "question": {"oneOf": [_QUESTION_SCHEMA, {"type": "null"}]},
        "resolved": {"type": "array", "items": {"type": "string"}},
        "open_points": {"type": "array", "items": {"type": "string"}},
        "awaiting_confirmation": {"type": "boolean"},
        "ready": {"type": "boolean"},
        "draft_update": _draft_update_schema(),
    },
}
