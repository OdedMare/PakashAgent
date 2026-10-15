"""Translate narrow natural-language requests into deterministic inputs."""

import json
from typing import Any, List, Optional

from app.bl.scheduler.slots import build_slots
from app.bl.scheduler.span_audit import usage_of
from app.bl.scheduler.values import bounded


DIRECTIVE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["directives", "unresolved"],
    "properties": {
        "directives": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source_id", "action", "employee", "date", "shift", "reason"],
                "properties": {
                    "source_id": {"type": "string"},
                    "action": {"type": "string", "enum": ["unavailable", "required_assignment"]},
                    "employee": {"type": "string"},
                    "date": {"type": "string"},
                    "shift": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "unresolved": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source_id", "reason"],
                "properties": {
                    "source_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
    },
}

_TEXT_POLICIES = (
    "dependencies", "casual_worker_policy", "rest_policy", "weekend_policy",
    "fairness_policy", "conflict_policy",
)
_EMPLOYEE_SEMANTICS = ("notes", "availability", "workload", "trainers", "is_trainee")


def semantic_sources(profile, availability=None, instructions="", preferences=None) -> List[dict]:
    """Every semantic input that code would otherwise have to ignore."""
    sources = []

    def add(kind: str, value: Any, context: str = "") -> None:
        if value in (None, "", [], {}, False):
            return
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        sources.append({
            "id": "source-%d" % (len(sources) + 1),
            "kind": kind,
            "context": context,
            "text": rendered,
        })

    add("instructions", instructions)
    for row in preferences or []:
        add("preference", row.get("text") if isinstance(row, dict) else row,
            bounded(row.get("subject")) if isinstance(row, dict) else "")
    for row in (profile or {}).get("rules") or []:
        add("rule", row)
    for key in _TEXT_POLICIES:
        add(key, (profile or {}).get(key))
    workplace = (profile or {}).get("workplace") or {}
    add("general_exit_schedule", workplace.get("general_exit_schedule"))
    training = (profile or {}).get("training_policy") or {}
    if training.get("shadow_shift_fraction") or training.get("shadow_shifts_per_week"):
        add("training_policy", training)
    for person in (profile or {}).get("employees") or []:
        if not isinstance(person, dict):
            continue
        name = bounded(person.get("name"))
        for key in _EMPLOYEE_SEMANTICS:
            add("employee_" + key, person.get(key), name)
        for row in person.get("recurring_constraints") or []:
            if isinstance(row, str) or (isinstance(row, dict) and row.get("is_hard", True) is False):
                add("recurring_constraint", row, name)
    for row in availability or []:
        if isinstance(row, dict) and row.get("is_hard", True) is False:
            add("soft_availability", row, bounded(row.get("employee")))
    return sources


def read_translation(answer: Any, sources: List[dict], profile: dict,
                     starts_on: str, ends_on: str) -> Optional[dict]:
    """Validate model output against the real roster and slot grid."""
    if not isinstance(answer, dict):
        return None
    directives, unresolved = answer.get("directives"), answer.get("unresolved")
    if not isinstance(directives, list) or not isinstance(unresolved, list):
        return None
    source_ids = {row["id"] for row in sources}
    covered, unresolved_ids = set(), set()
    for row in unresolved:
        if not isinstance(row, dict) or row.get("source_id") not in source_ids or not bounded(row.get("reason")):
            return None
        unresolved_ids.add(row["source_id"])
    if unresolved_ids:
        return None

    people = {
        bounded(row.get("name")): row for row in (profile or {}).get("employees") or []
        if isinstance(row, dict) and bounded(row.get("name"))
    }
    slots = {
        (row["shift_name"], row["slot_date"])
        for row in build_slots(profile, starts_on, ends_on)
    }
    translated_availability, required = [], []
    for row in directives:
        if not isinstance(row, dict):
            return None
        source_id = row.get("source_id")
        action, employee = row.get("action"), bounded(row.get("employee"))
        date, shift, reason = bounded(row.get("date")), bounded(row.get("shift")), bounded(row.get("reason"))
        if (source_id not in source_ids or action not in ("unavailable", "required_assignment")
                or employee not in people or (shift, date) not in slots or not reason):
            return None
        allowed = people[employee].get("eligible_shifts")
        if action == "required_assignment" and isinstance(allowed, list) and allowed and shift not in allowed:
            return None
        covered.add(source_id)
        if action == "unavailable":
            translated_availability.append({
                "employee": employee, "date": date, "shift": shift,
                "available": False, "is_hard": True, "reason": reason,
                "source": "llm_directive",
            })
        else:
            required.append({
                "employee": employee, "date": date, "shift": shift,
                "reason": reason,
            })
    if covered != source_ids:
        return None
    return {
        "availability": translated_availability,
        "required_assignments": required,
        "usage": usage_of(answer),
    }


__all__ = ["DIRECTIVE_RESPONSE_SCHEMA", "read_translation", "semantic_sources"]
