"""Translate narrow natural-language requests into deterministic inputs."""

import json
from typing import Any, List, Optional

from app.bl.schedule_requests import KINDS, PERIODS, read_requests
from app.bl.scheduler.slots import build_slots
from app.bl.scheduler.span_audit import usage_of
from app.bl.scheduler.values import bounded


DIRECTIVE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["directives", "requests", "unresolved"],
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
        "requests": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "source_id", "kind", "employees", "shifts", "dates", "weekdays",
                    "count", "per", "is_hard", "weight", "reason",
                ],
                "properties": {
                    "source_id": {"type": "string"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "employees": {"type": "array", "items": {"type": "string"}},
                    "shifts": {"type": "array", "items": {"type": "string"}},
                    "dates": {"type": "array", "items": {"type": "string"}},
                    "weekdays": {"type": "array", "items": {"type": "string"}},
                    "count": {"type": ["integer", "null"]},
                    "per": {"type": "string", "enum": list(PERIODS)},
                    "is_hard": {"type": "boolean"},
                    "weight": {"type": "number"},
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
    """Every semantic input that code would otherwise have to ignore.

    `binding` says whether code may build without a source it could not
    translate. Only what is soft by its own definition is not binding: a
    rule the manager tagged soft (D1) and a preference (D21). Everything
    else, the manager's free instruction included, is treated as binding,
    because dropping a "must" silently is the one outcome worse than paying
    for the full scheduler.
    """
    sources = []

    def add(kind: str, value: Any, context: str = "", binding: bool = True) -> None:
        if value in (None, "", [], {}, False):
            return
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        sources.append({
            "id": "source-%d" % (len(sources) + 1),
            "kind": kind,
            "context": context,
            "text": rendered,
            "binding": binding,
        })

    add("instructions", instructions)
    for row in preferences or []:
        add("preference", row.get("text") if isinstance(row, dict) else row,
            bounded(row.get("subject")) if isinstance(row, dict) else "", binding=False)
    for row in (profile or {}).get("rules") or []:
        add("rule", row, binding=not (isinstance(row, dict) and row.get("priority") == "soft"))
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
        # Soft structured constraints are already code's to weigh
        # (`deterministic_scheduler/honoring.py`); only sentences need reading.
        for row in person.get("recurring_constraints") or []:
            if isinstance(row, str):
                add("recurring_constraint", row, name)
    return sources


def _unresolved_ids(rows, source_ids):
    found = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("source_id") not in source_ids \
                or not bounded(row.get("reason")):
            return None
        found.add(row["source_id"])
    return found


def translated_row(row, source_ids, people, slots):
    if not isinstance(row, dict):
        return None
    source_id = row.get("source_id")
    action, employee = row.get("action"), bounded(row.get("employee"))
    date, shift = bounded(row.get("date")), bounded(row.get("shift"))
    reason = bounded(row.get("reason"))
    if (source_id not in source_ids or action not in ("unavailable", "required_assignment")
            or employee not in people or (shift, date) not in slots or not reason):
        return None
    allowed = people[employee].get("eligible_shifts")
    if action == "required_assignment" and isinstance(allowed, list) and allowed and shift not in allowed:
        return None
    if action == "unavailable":
        value = {"employee": employee, "date": date, "shift": shift,
                 "available": False, "is_hard": True, "reason": reason,
                 "source": "llm_directive"}
    else:
        value = {"employee": employee, "date": date, "shift": shift, "reason": reason}
    return source_id, action, value


def read_translation(answer: Any, sources: List[dict], profile: dict,
                     starts_on: str, ends_on: str) -> Optional[dict]:
    """Validate model output against the real roster and slot grid."""
    if not isinstance(answer, dict):
        return None
    directives, unresolved = answer.get("directives"), answer.get("unresolved")
    if not isinstance(directives, list) or not isinstance(unresolved, list):
        return None
    source_ids = {row["id"] for row in sources}
    unresolved_ids = _unresolved_ids(unresolved, source_ids)
    if unresolved_ids is None:
        return None
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
    requests, errors = read_requests(answer.get("requests") or [], profile)
    if errors or any(row["source_id"] not in source_ids for row in requests):
        return None
    translated_availability, required = [], []
    covered = {row["source_id"] for row in requests}
    for row in directives:
        translated = translated_row(row, source_ids, people, slots)
        if translated is None:
            return None
        source_id, action, value = translated
        covered.add(source_id)
        if action == "unavailable":
            translated_availability.append(value)
        else:
            required.append(value)
    if covered != source_ids:
        return None
    return {
        "availability": translated_availability,
        "required_assignments": required,
        "requests": requests,
        "usage": usage_of(answer),
    }


__all__ = ["DIRECTIVE_RESPONSE_SCHEMA", "read_translation", "semantic_sources", "translated_row"]
