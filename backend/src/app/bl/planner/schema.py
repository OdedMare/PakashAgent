"""The shape of one planner turn: an answer, a question, or tool calls."""

from app.bl.tools import TOOL_NAMES

# How many tools may run in a single turn. Bounded because the model names
# them and an unbounded list is an unbounded number of repository reads.
MAX_CALLS_PER_TURN = 4
MAX_OPTIONS = 4

_TOOL_CALL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tool", "arguments"],
    "properties": {
        "tool": {"type": "string", "enum": list(TOOL_NAMES)},
        "arguments": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "employee": {"type": "string"},
                "shift_name": {"type": "string"},
                "slot_date": {"type": "string"},
                "day": {"type": "string"},
                "starts_on": {"type": "string"},
                "ends_on": {"type": "string"},
                "timezone": {"type": "string"},
                "schedule_id": {"type": "string"},
                "moving_assignment_id": {"type": "string"},
            },
        },
    },
}

_QUESTION_SCHEMA = {
    "type": ["object", "null"],
    "additionalProperties": False,
    "required": ["question", "recommendation", "why", "options"],
    "properties": {
        "question": {"type": "string"},
        "recommendation": {"type": "string"},
        "why": {"type": "string"},
        "options": {
            "type": "array",
            "maxItems": MAX_OPTIONS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "answer"],
                "properties": {
                    "label": {"type": "string"},
                    "answer": {"type": "string"},
                },
            },
        },
    },
}

PLANNER_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "done", "answer", "question", "tool_calls", "needs_confirmation",
        "needs_input",
    ],
    "properties": {
        # The model's own statement that it has what it needs. Bounded in
        # code by the turn limit regardless, so a model that never sets it
        # still terminates.
        "done": {"type": "boolean"},
        "answer": {"type": "string"},
        "question": _QUESTION_SCHEMA,
        "tool_calls": {
            "type": "array",
            "items": _TOOL_CALL_SCHEMA,
            "maxItems": MAX_CALLS_PER_TURN,
        },
        # True when what is being described *would* change the schedule, so
        # the manager is told plainly that nothing has happened yet. A label
        # on a sentence, not a queued operation -- there is no operation
        # anywhere in this schema.
        "needs_confirmation": {"type": "boolean"},
        # An ambiguous request is not a failed answer. It is one focused
        # question that keeps the conversation moving without guessing.
        "needs_input": {"type": "boolean"},
    },
}
