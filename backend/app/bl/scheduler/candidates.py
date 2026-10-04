"""Legal choices per slot, and the response schema that can only name them.

Each span's payload names people and slots by small prompt-local ids, and the
schema enumerates exactly those ids -- so a model answering with someone who
is unavailable, or a slot that does not exist, fails the schema rather than
the audit.
"""

from typing import Any, List, Optional

from app.bl.audit import constraint_conflicts, counts_toward_staffing
from app.bl.scheduler.bounding import bound_assignments
from app.bl.scheduler.values import bounded


def slot_id(index: int) -> str:
    return "slot-%d" % index


def candidates_for(
    profile: dict, slots: List[dict], availability: List[dict]
) -> dict:
    """Legal employee choices per slot, with small stable prompt-local ids."""
    employees, id_by_name = _candidate_employees(profile)
    hard = [
        item for item in availability
        if isinstance(item, dict) and item.get("is_hard", True) is not False
    ]
    by_slot = {
        slot_id(index): _eligible(profile, slot, hard, id_by_name)
        for index, slot in enumerate(slots, 1)
    }
    return {
        "employees": employees,
        "id_by_name": id_by_name,
        "name_by_id": {value: key for key, value in id_by_name.items()},
        "by_slot": by_slot,
    }


def _candidate_employees(profile: dict) -> tuple:
    employees, id_by_name = [], {}
    for index, person in enumerate((profile or {}).get("employees") or [], 1):
        if not isinstance(person, dict) or not bounded(person.get("name")):
            continue
        employee_id = "employee-%d" % index
        id_by_name[bounded(person.get("name"))] = employee_id
        employees.append(_candidate(person, employee_id, profile))
    return employees, id_by_name


def _candidate(person: dict, employee_id: str, profile: dict) -> dict:
    return {
        "id": employee_id,
        "name": bounded(person.get("name")),
        "role": person.get("role") or person.get("roles") or "",
        "eligible_shifts": person.get("eligible_shifts") or [],
        "max_weekly_hours": person.get("max_weekly_hours") or 0,
        "is_trainee": bool(person.get("is_trainee")),
        "is_shift_manager": bool(person.get("is_shift_manager")),
        "can_train": bool(person.get("can_train")),
        "exit_pattern": person.get("exit_pattern") or "",
        "rotation_group": person.get("rotation_group") or "",
        "notes": person.get("notes") or "",
        # The audit's own rule, imported rather than restated: this is what
        # the model is told a shadow shift means, and the warning it gets
        # judged by has to mean the same thing.
        "counts_toward_staffing": counts_toward_staffing(person, profile),
    }


def _eligible(
    profile: dict, slot: dict, hard: List[dict], id_by_name: dict
) -> List[str]:
    eligible = []
    for person in (profile or {}).get("employees") or []:
        if not isinstance(person, dict):
            continue
        name = bounded(person.get("name"))
        allowed = person.get("eligible_shifts")
        if isinstance(allowed, list) and allowed and slot["shift_name"] not in allowed:
            continue
        placed = {
            "employee": name,
            "date": slot["slot_date"],
            "shift": slot["shift_name"],
            "start_time": slot.get("start_time"),
            "end_time": slot.get("end_time"),
        }
        if any(constraint_conflicts(placed, item) for item in hard):
            continue
        if name in id_by_name:
            eligible.append(id_by_name[name])
    return eligible


def span_schema(slots: List[dict], candidates: dict) -> dict:
    """A response schema whose ids can only name this span's actual choices."""
    employee_ids = [item["id"] for item in candidates["employees"]]
    assignment = {
        "type": "object",
        "additionalProperties": False,
        "required": ["employee_id", "slot_id", "reason"],
        "properties": {
            "employee_id": (
                {"type": "string", "enum": employee_ids}
                if employee_ids else {"type": "string"}
            ),
            "slot_id": {
                "type": "string",
                "enum": [slot_id(index) for index in range(1, len(slots) + 1)],
            },
            "reason": {"type": "string", "minLength": 4},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["assignments", "notes", "summary"],
        "properties": {
            "assignments": {
                "type": "array",
                # Non-counting trainees may be assigned in addition to the
                # required headcount, so permit every legal candidate once.
                "maxItems": sum(
                    len(candidates["by_slot"].get(slot_id(index), []))
                    for index, _ in enumerate(slots, 1)
                ),
                "items": assignment,
            },
            "notes": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
    }


def read_span_assignments(
    offered: Any, slots: List[dict], profile: dict, candidates: dict,
    availability: Optional[List[dict]] = None,
) -> tuple:
    """Translate prompt-local ids and retain an auditable rejection count."""
    if not isinstance(offered, list):
        return [], [{"reason": "assignments is not a list"}]
    slot_by_id = {slot_id(index): slot for index, slot in enumerate(slots, 1)}
    translated, rejected = [], []
    for item in offered:
        if not isinstance(item, dict):
            rejected.append({"reason": "row is not an object"})
            continue
        row = _translate(item, slot_by_id, candidates)
        if row is None:
            rejected.append({
                "employee_id": bounded(item.get("employee_id")),
                "slot_id": bounded(item.get("slot_id")),
                "reason": "unknown or ineligible candidate",
            })
            continue
        translated.append(row)
    accepted = bound_assignments(translated, slots, profile, availability)
    rejected.extend(
        {"reason": "missing reason, duplicate, or unknown slot/person"}
        for _ in range(len(translated) - len(accepted))
    )
    return accepted, rejected


def _translate(item: dict, slot_by_id: dict, candidates: dict) -> Optional[dict]:
    """An id-keyed row as a named one; None when the ids name no legal pair.

    A row carrying names instead of ids is passed through unchanged --
    backward-compatible with older servers and scripted tests while the
    prompt contract rolls forward to ids.
    """
    employee_id = bounded(item.get("employee_id"))
    wanted_slot = bounded(item.get("slot_id"))
    if not employee_id and not wanted_slot:
        return item
    slot = slot_by_id.get(wanted_slot)
    if slot is None or employee_id not in candidates["by_slot"].get(wanted_slot, []):
        return None
    return {
        "employee": candidates["name_by_id"].get(employee_id, ""),
        "shift": slot["shift_name"],
        "date": slot["slot_date"],
        "reason": item.get("reason"),
    }
