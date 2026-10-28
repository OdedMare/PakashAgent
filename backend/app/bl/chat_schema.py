"""The existing JSON model protocol, extended for one manager conversation."""

import copy
import re

from app.bl.changes.schema import CHANGE_RESPONSE_SCHEMA
from app.bl.chat_contract import approval_text
from app.bl.planner.schema import _QUESTION_SCHEMA, _TOOL_CALL_SCHEMA

CHAT_SCHEMA = copy.deepcopy(CHANGE_RESPONSE_SCHEMA)
props = CHAT_SCHEMA["properties"]
props.update({
    "kind": {"type": "string", "enum": [
        "answer", "changes", "profile", "generate", "publish", "unpublish", "clear", "retire", "restructure", "manage", "blank", "delete_period",
    ]},
    "schedule_id": {"type": "string"},
    "stated_reason": {"type": "string"},
    "profile_patch_json": {"type": "string"},
    "starts_on": {"type": "string"},
    "ends_on": {"type": "string"},
    "copy_from_date": {"type": "string"},
    "employee": {"type": "string"},
    "effective_date": {"type": "string"},
    "instructions": {"type": "string"},
    "replace_existing": {"type": "boolean"},
    "leave_vacant": {"type": "boolean"},
    "required_assignments": {"type": "array", "maxItems": 2000, "items": {
        "type": "object", "additionalProperties": False,
        "properties": {key: {"type": "string"} for key in ("employee", "shift", "date")},
        "required": ["employee", "shift", "date"],
    }},
    "exceptions": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
    "suggestions": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 80}},
    "question": copy.deepcopy(_QUESTION_SCHEMA),
    "tool_calls": {"type": "array", "maxItems": 4, "items": copy.deepcopy(_TOOL_CALL_SCHEMA)},
    "management_operations": {"type": "array", "maxItems": 20, "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "resource": {"type": "string", "enum": ["constraint_request", "swap_request", "preference"]},
            "action": {"type": "string", "enum": ["approve", "reject", "add", "update", "archive", "delete"]},
            **{key: {"type": "string"} for key in ("id", "text", "kind", "subject", "reason")},
        },
        "required": ["resource", "action"],
    }},
})
props["tool_calls"]["items"]["properties"]["tool"]["enum"] += [
    "list_periods", "workload_report", "change_history", "simulate_changes",
    "constraints_report", "request_inbox", "preference_list",
]
props["tool_calls"]["items"]["properties"]["arguments"]["properties"]["operations"] = \
    copy.deepcopy(props["operations"])
props["needs_reason"]["enum"] = [False]
props["reply"]["minLength"] = 1
props["constraints"]["items"]["properties"]["available"] = {"type": "boolean"}
props["constraints"]["items"]["properties"].update({
    "action": {"type": "string", "enum": ["set", "remove"]},
    "id": {"type": "string"},
    "start_time": {"type": "string"}, "end_time": {"type": "string"},
    "is_hard": {"type": "boolean"},
    "constraint_type": {"type": "string", "enum": ["availability", "duty"]},
})
props["constraints"]["maxItems"] = 126
CHAT_SCHEMA["required"] = list(props)

PROFILE_SECTIONS = (
    "workplace", "employees", "shifts", "rules", "dependencies", "training_policy",
    "audit_policy", "availability_process", "constraint_deadline", "casual_worker_policy",
    "rest_policy", "weekend_policy", "fairness_policy", "conflict_policy",
    "existing_schedule_source", "summary",
)


# A suggestion is a button that sends its text as the manager's next message.
# One that reads as approval would turn a click on "an idea" into consent to
# the pending plan (`chat_contract.approval_text`), so anything approving,
# confirming or executing is dropped here rather than trusted to the prompt.
_APPROVING = re.compile(r"אשר|אישור|מאושר|תבצע|לבצע|^כן(?!\S)")
_MAX_SUGGESTIONS = 3
_MAX_SUGGESTION_LENGTH = 80


def suggestions(values):
    """The model's follow-up ideas, safe to offer as one-click messages."""
    kept = []
    for value in values or []:
        text = " ".join(str(value or "").split())
        if not text or len(text) > _MAX_SUGGESTION_LENGTH \
                or _APPROVING.search(text) or approval_text(text):
            continue
        if text not in kept:
            kept.append(text)
    return kept[:_MAX_SUGGESTIONS]
