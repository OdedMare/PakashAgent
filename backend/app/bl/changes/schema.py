"""What a proposal may contain: schedule operations, constraints, profile edits."""

MAX_OPERATIONS = 40
MAX_PROFILE_OPERATIONS = 10

# What a proposal may ask for. Deliberately small: these three cover every
# change the product handles, and an operation vocabulary that grows past
# what the schedule can actually express is a way for a proposal to describe
# something no code can apply.
OP_ASSIGN = "assign"
OP_REMOVE = "remove"
OP_SWAP = "swap"
OPERATIONS = (OP_ASSIGN, OP_REMOVE, OP_SWAP)
PROFILE_ADD_EMPLOYEE = "add_employee"
PROFILE_UPDATE_EMPLOYEE = "update_employee"
PROFILE_ADD_SHIFT = "add_shift"
PROFILE_UPDATE_SHIFT = "update_shift"
PROFILE_OPERATIONS = (
    PROFILE_ADD_EMPLOYEE, PROFILE_UPDATE_EMPLOYEE,
    PROFILE_ADD_SHIFT, PROFILE_UPDATE_SHIFT,
)

_OPERATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "employee", "shift", "date", "reason"],
    "properties": {
        "action": {"type": "string", "enum": list(OPERATIONS)},
        "employee": {"type": "string"},
        "shift": {"type": "string"},
        "date": {"type": "string"},
        # The other half of a swap. Empty on assign and remove.
        "with_employee": {"type": "string"},
        "with_shift": {"type": "string"},
        "with_date": {"type": "string"},
        "reason": {"type": "string"},
    },
}

_CONSTRAINT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["employee", "date", "shift", "reason"],
    "properties": {
        "employee": {"type": "string"},
        "date": {"type": "string"},
        # Empty means the whole day, the same convention the interview and
        # `audit.py` use.
        "shift": {"type": "string"},
        "reason": {"type": "string"},
    },
}

_PROFILE_ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "name", "role", "eligible_shifts", "start_time", "end_time",
        "headcount", "is_on_call",
    ],
    "properties": {
        "name": {"type": "string"},
        "role": {"type": "string"},
        "eligible_shifts": {"type": "array", "items": {"type": "string"}},
        "start_time": {"type": "string"},
        "end_time": {"type": "string"},
        "headcount": {"type": "integer"},
        "is_on_call": {"type": "boolean"},
    },
}

_PROFILE_OPERATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "target", "item"],
    "properties": {
        "action": {"type": "string", "enum": list(PROFILE_OPERATIONS)},
        "target": {"type": "string"},
        "item": _PROFILE_ITEM_SCHEMA,
    },
}

CHANGE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "reply", "needs_reason", "needs_input", "agent_reason", "operations",
        "constraints", "profile_operations",
    ],
    "properties": {
        "reply": {"type": "string"},
        # True when the manager has not said why. The answer is a question
        # back, never a rejection and never a guess.
        "needs_reason": {"type": "boolean"},
        # True when the request cannot be carried out without guessing *what
        # it refers to*. A different gap from `needs_reason`: that one is
        # missing *why*, this one is missing *what* (D24).
        "needs_input": {"type": "boolean"},
        "agent_reason": {"type": "string"},
        "operations": {
            "type": "array", "items": _OPERATION_SCHEMA,
            "maxItems": MAX_OPERATIONS,
        },
        "constraints": {"type": "array", "items": _CONSTRAINT_SCHEMA},
        "profile_operations": {
            "type": "array", "items": _PROFILE_OPERATION_SCHEMA,
            "maxItems": MAX_PROFILE_OPERATIONS,
        },
    },
}
