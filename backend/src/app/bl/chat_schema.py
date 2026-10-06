"""The existing JSON model protocol, extended for one manager conversation."""

import copy

from app.bl.changes.schema import CHANGE_RESPONSE_SCHEMA
from app.bl.planner.schema import _QUESTION_SCHEMA, _TOOL_CALL_SCHEMA

CHAT_SCHEMA = copy.deepcopy(CHANGE_RESPONSE_SCHEMA)
props = CHAT_SCHEMA["properties"]
props.update({
    "kind": {"type": "string", "enum": [
        "answer", "changes", "profile", "generate", "publish", "unpublish", "clear",
    ]},
    "schedule_id": {"type": "string"},
    "stated_reason": {"type": "string"},
    "profile_patch_json": {"type": "string"},
    "starts_on": {"type": "string"},
    "ends_on": {"type": "string"},
    "instructions": {"type": "string"},
    "replace_existing": {"type": "boolean"},
    "required_assignments": {"type": "array", "maxItems": 2000, "items": {
        "type": "object", "additionalProperties": False,
        "properties": {key: {"type": "string"} for key in ("employee", "shift", "date")},
        "required": ["employee", "shift", "date"],
    }},
    "exceptions": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
    "question": copy.deepcopy(_QUESTION_SCHEMA),
    "tool_calls": {"type": "array", "maxItems": 4, "items": copy.deepcopy(_TOOL_CALL_SCHEMA)},
})
props["tool_calls"]["items"]["properties"]["tool"]["enum"] += [
    "list_periods", "workload_report", "change_history", "simulate_changes",
]
props["tool_calls"]["items"]["properties"]["arguments"]["properties"]["operations"] = \
    copy.deepcopy(props["operations"])
props["needs_reason"]["enum"] = [False]
props["constraints"]["items"]["properties"]["available"] = {"type": "boolean"}
CHAT_SCHEMA["required"] = list(props)

PROFILE_SECTIONS = (
    "workplace", "employees", "shifts", "rules", "dependencies", "training_policy",
    "audit_policy", "availability_process", "constraint_deadline", "casual_worker_policy",
    "rest_policy", "weekend_policy", "fairness_policy", "conflict_policy",
    "existing_schedule_source", "summary",
)
