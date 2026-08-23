"""Conversational edits to a live schedule, and the change log behind them.

The step-4 loop: *"דנה חולה ביום חמישי."*

1. Parse the request.
2. **If the manager gave no reason, ask for one.** Required
   ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)) — and
   asked for rather than rejected, because a manager who omitted a reason
   made an omission, not an error.
3. Propose a replacement **with the agent's justification**.
4. On confirmation: apply in place, append to the log.

Proposing and applying are deliberately two calls. The manager confirms in
between, and that gap is the whole point: under D3 the agent's judgment is
final, so seeing *why* it picked this person is the manager's one cheap
chance to catch a bad call.

This module proposes. It does not write — `schedule_service.py` applies a
proposal the manager has confirmed, which is what keeps "the agent decided"
and "the manager agreed" as two separate, auditable events.
"""

import datetime
import json
from typing import Any, Dict, List, Optional

from app.bl.prompts import load
from app.common.errors import AgentError

_MAX_TEXT_CHARS = 4000
_MAX_OPERATIONS = 40

# What a proposal may ask for. Deliberately small: these three cover every
# change the product handles, and an operation vocabulary that grows past
# what the schedule can actually express is a way for a proposal to describe
# something no code can apply.
OP_ASSIGN = "assign"
OP_REMOVE = "remove"
OP_SWAP = "swap"
_OPERATIONS = (OP_ASSIGN, OP_REMOVE, OP_SWAP)
PROFILE_ADD_EMPLOYEE = "add_employee"
PROFILE_UPDATE_EMPLOYEE = "update_employee"
PROFILE_ADD_SHIFT = "add_shift"
PROFILE_UPDATE_SHIFT = "update_shift"
_PROFILE_OPERATIONS = (
    PROFILE_ADD_EMPLOYEE, PROFILE_UPDATE_EMPLOYEE,
    PROFILE_ADD_SHIFT, PROFILE_UPDATE_SHIFT,
)

_OPERATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "employee", "shift", "date", "reason"],
    "properties": {
        "action": {"type": "string", "enum": list(_OPERATIONS)},
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
        "action": {"type": "string", "enum": list(_PROFILE_OPERATIONS)},
        "target": {"type": "string"},
        "item": _PROFILE_ITEM_SCHEMA,
    },
}

CHANGE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "reply", "needs_reason", "agent_reason", "operations", "constraints",
        "profile_operations",
    ],
    "properties": {
        "reply": {"type": "string"},
        # True when the manager has not said why. The answer is a question
        # back, never a rejection and never a guess.
        "needs_reason": {"type": "boolean"},
        "agent_reason": {"type": "string"},
        "operations": {
            "type": "array", "items": _OPERATION_SCHEMA,
            "maxItems": _MAX_OPERATIONS,
        },
        "constraints": {"type": "array", "items": _CONSTRAINT_SCHEMA},
        "profile_operations": {
            "type": "array", "items": _PROFILE_OPERATION_SCHEMA,
            "maxItems": 10,
        },
    },
}


class ChangeAgent:
    """Turn a manager's sentence into a proposal they can confirm."""

    def __init__(self, llm):
        self._llm = llm

    def propose(
        self,
        profile: dict,
        schedule: dict,
        request: str,
        stated_reason: str = "",
        availability: Optional[List[dict]] = None,
        history: Optional[List[dict]] = None,
    ) -> dict:
        """What the agent would do, and why. Applies nothing."""
        text = _bounded(request)
        if not text:
            raise AgentError("הבקשה אינה יכולה להיות ריקה")
        payload = {
            "profile": _profile_for_model(profile),
            "schedule": _schedule_for_model(schedule),
            "availability": _rows(availability),
            "history": _rows(history, 100),
            "request": text,
            "stated_reason": _bounded(stated_reason),
        }
        answer = self._ask(payload)
        return _proposal(answer, profile, schedule, _bounded(stated_reason))

    def _ask(self, payload: dict) -> dict:
        answer = self._llm.complete_json(
            load("changes"),
            json.dumps(payload, ensure_ascii=False, default=_json_default),
            schema=CHANGE_RESPONSE_SCHEMA,
            flow="changes",
        )
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר הצעת שינוי לא תקינה")
        return answer


def _proposal(
    answer: dict, profile: dict, schedule: dict, stated_reason: str
) -> dict:
    """The model's turn, bounded, with the reason gate enforced in code.

    `needs_reason` is not left to the prompt alone: a proposal that would
    change the roster without the manager having said why is withdrawn here
    and turned back into a question. D8 is the decision this protects, and a
    model that forgets it once would otherwise write an unexplained change
    into the only history the system keeps.
    """
    operations = _operations(answer.get("operations"), schedule)
    profile_operations = _profile_operations(
        answer.get("profile_operations"), profile
    )
    needs_reason = bool(answer.get("needs_reason")) and not stated_reason
    if operations and not stated_reason and not answer.get("agent_reason"):
        needs_reason = True
    if needs_reason:
        # A question, not a rejection: the manager omitted something, and
        # the product's answer to an omission is to ask.
        operations = []
    if profile_operations:
        operations = []
        needs_reason = False
    return {
        "reply": _bounded(answer.get("reply")),
        "needs_reason": needs_reason,
        "agent_reason": _bounded(answer.get("agent_reason")),
        "stated_reason": stated_reason,
        "operations": operations,
        "profile_operations": profile_operations,
        "constraints": _constraints(answer.get("constraints")),
    }


def _operations(offered: Any, schedule: dict) -> List[dict]:
    """Operations bounded to slots this schedule actually has.

    A move naming a shift or date the period does not contain has nothing to
    apply to, so it is dropped rather than half-applied later. That is a
    check on whether the target exists, not on whether the choice was good —
    the audit is what comments on the choice.
    """
    if not isinstance(offered, list):
        return []
    slots = {
        (_bounded(slot.get("shift_name")), _date(slot.get("slot_date")))
        for slot in (schedule or {}).get("slots") or []
    }
    if not slots:
        return []
    operations = []
    for item in offered[:_MAX_OPERATIONS]:
        if not isinstance(item, dict):
            continue
        action = _bounded(item.get("action"))
        employee = _bounded(item.get("employee"))
        shift = _bounded(item.get("shift"))
        date = _date(item.get("date"))
        if action not in _OPERATIONS or not employee or not date:
            continue
        if slots and (shift, date) not in slots:
            continue
        operation = {
            "action": action,
            "employee": employee,
            "shift": shift,
            "date": date,
            "reason": _bounded(item.get("reason")),
        }
        if action == OP_SWAP:
            with_employee = _bounded(item.get("with_employee"))
            with_shift = _bounded(item.get("with_shift")) or shift
            with_date = _date(item.get("with_date")) or date
            if not with_employee:
                continue
            if slots and (with_shift, with_date) not in slots:
                continue
            operation.update({
                "with_employee": with_employee,
                "with_shift": with_shift,
                "with_date": with_date,
            })
        operations.append(operation)
    return operations


def _profile_operations(offered: Any, profile: dict) -> List[dict]:
    """Bound profile edits to the four operations the UI can also perform."""
    if not isinstance(offered, list):
        return []
    employee_names = {
        _bounded(row.get("name")) for row in (profile or {}).get("employees") or []
        if isinstance(row, dict)
    }
    shift_names = {
        _bounded(row.get("name")) for row in (profile or {}).get("shifts") or []
        if isinstance(row, dict)
    }
    result = []
    for raw in offered[:10]:
        if not isinstance(raw, dict):
            continue
        action = _bounded(raw.get("action"))
        target = _bounded(raw.get("target"))
        item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
        item = {
            "name": _bounded(item.get("name")),
            "role": _bounded(item.get("role")),
            "eligible_shifts": [
                _bounded(value) for value in item.get("eligible_shifts") or []
                if _bounded(value)
            ],
            "start_time": _bounded(item.get("start_time")),
            "end_time": _bounded(item.get("end_time")),
            "headcount": item.get("headcount") or 1,
            "is_on_call": bool(item.get("is_on_call")),
        }
        name = item["name"]
        if action not in _PROFILE_OPERATIONS or not name:
            continue
        if action == PROFILE_ADD_EMPLOYEE and name in employee_names:
            continue
        if action == PROFILE_UPDATE_EMPLOYEE and target not in employee_names:
            continue
        if action == PROFILE_ADD_SHIFT and name in shift_names:
            continue
        if action == PROFILE_UPDATE_SHIFT and target not in shift_names:
            continue
        result.append({"action": action, "target": target, "item": item})
    return result


def _constraints(offered: Any) -> List[dict]:
    """Constraints the request implied, to be remembered rather than
    worked around once.

    "דנה חולה ביום חמישי" is both a change and a fact about Thursday. Storing
    the fact is what stops the next schedule from putting her right back.
    """
    if not isinstance(offered, list):
        return []
    constraints = []
    for item in offered:
        if not isinstance(item, dict):
            continue
        employee = _bounded(item.get("employee"))
        date = _date(item.get("date"))
        if not employee or not date:
            continue
        constraints.append({
            "employee": employee,
            "date": date,
            "shift": _bounded(item.get("shift")),
            "reason": _bounded(item.get("reason")),
        })
    return constraints


def _profile_for_model(profile: dict) -> dict:
    profile = profile if isinstance(profile, dict) else {}
    return {
        "workplace": profile.get("workplace") or {},
        "employees": profile.get("employees") or [],
        "shifts": profile.get("shifts") or [],
        "rules": profile.get("rules") or [],
        "rest_policy": profile.get("rest_policy") or "",
        "fairness_policy": profile.get("fairness_policy") or "",
        "conflict_policy": profile.get("conflict_policy") or "",
    }


def _schedule_for_model(schedule: dict) -> dict:
    """The period as the model reads it: slots, and who is on each."""
    schedule = schedule if isinstance(schedule, dict) else {}
    return {
        "starts_on": _date(schedule.get("starts_on")),
        "ends_on": _date(schedule.get("ends_on")),
        "slots": [
            {
                "shift": _bounded(slot.get("shift_name")),
                "date": _date(slot.get("slot_date")),
                "headcount": slot.get("headcount", 1),
            }
            for slot in schedule.get("slots") or []
        ],
        "assignments": [
            {
                "employee": _bounded(row.get("employee")),
                "shift": _bounded(row.get("shift")),
                "date": _date(row.get("date")),
                "reason": _bounded(row.get("reason")),
            }
            for row in schedule.get("assignments") or []
        ],
    }


def _rows(rows: Any, limit: int = 200) -> List[dict]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)][-limit:]


def _date(value: Any) -> str:
    """A date as `YYYY-MM-DD`, however the row happened to carry it.

    Repository rows come back as `datetime.date` and model output as strings;
    both are compared against each other here, so both are normalized to the
    one shape rather than trusting them to already match.
    """
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _bounded(value)


def _json_default(value: Any) -> str:
    """SQL temporal values as JSON strings in raw availability/history rows."""
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    raise TypeError(
        "Object of type %s is not JSON serializable"
        % value.__class__.__name__
    )


def _bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


__all__ = [
    "ChangeAgent", "CHANGE_RESPONSE_SCHEMA",
    "OP_ASSIGN", "OP_REMOVE", "OP_SWAP",
    "PROFILE_ADD_EMPLOYEE", "PROFILE_UPDATE_EMPLOYEE",
    "PROFILE_ADD_SHIFT", "PROFILE_UPDATE_SHIFT",
]
