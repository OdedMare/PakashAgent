"""The shape of one translation turn: tool calls, or the translation itself.

A turn is the directive response the single-call translation always
returned, plus `calls`. A turn with calls asks for tool results and is not
an answer yet; a turn without them is the answer, read exactly as before by
`scheduler.directives.read_translation`.
"""

from app.bl.scheduler.directives import DIRECTIVE_RESPONSE_SCHEMA

TOOL_NAMES = ("resolve_employee", "list_slots", "employee_state", "check", "dry_run")

TOOL_DESCRIPTIONS = {
    "resolve_employee": "Which roster person a name means: one match, several, or none. "
                        "Arguments: name.",
    "list_slots": "The period's real slots, narrowed by dates (ISO), weekdays (Hebrew) "
                  "and shifts; any left empty means any.",
    "employee_state": "One person's eligible shifts, roles, shift-manager flag, rotation "
                      "group and hard unavailability in the period. Arguments: name.",
    "check": "Validate draft directives and requests against the roster and the slot "
             "grid without scheduling. Returns each refusal and the sources not yet covered.",
    "dry_run": "Schedule the period in memory with draft directives and requests applied. "
               "Returns staffing warnings and the soft requests code had to break. "
               "Persists nothing.",
}

# How many tools may run in one turn, and how many dry runs in one
# translation: each dry run schedules the whole period.
MAX_CALLS_PER_TURN = 4
MAX_DRY_RUNS = 2

_ITEMS = DIRECTIVE_RESPONSE_SCHEMA["properties"]

_CALL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tool", "arguments"],
    "properties": {
        "tool": {"type": "string", "enum": list(TOOL_NAMES)},
        "arguments": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "dates": {"type": "array", "items": {"type": "string"}},
                "weekdays": {"type": "array", "items": {"type": "string"}},
                "shifts": {"type": "array", "items": {"type": "string"}},
                "directives": _ITEMS["directives"],
                "requests": _ITEMS["requests"],
            },
        },
    },
}

TURN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["calls", "directives", "requests", "unresolved"],
    "properties": {
        "calls": {"type": "array", "maxItems": MAX_CALLS_PER_TURN, "items": _CALL_SCHEMA},
        "directives": _ITEMS["directives"],
        "requests": _ITEMS["requests"],
        "unresolved": _ITEMS["unresolved"],
    },
}

__all__ = [
    "MAX_CALLS_PER_TURN", "MAX_DRY_RUNS", "TOOL_DESCRIPTIONS", "TOOL_NAMES", "TURN_SCHEMA",
]
