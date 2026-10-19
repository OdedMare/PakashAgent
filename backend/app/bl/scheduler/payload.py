"""How the workplace and the period are shown to the model."""

from typing import List, Optional

from app.bl.scheduler.candidates import slot_id
from app.bl.audit.roster import is_night, shift_hours
from app.bl.scheduler.rotation_rows import closures_for_model as _closures
from app.bl.scheduler.values import parse_date, role_list

_ASSIGNMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["employee", "shift", "date", "reason"],
    "properties": {
        "employee": {"type": "string"},
        "shift": {"type": "string"},
        "date": {"type": "string"},
        # Required by the schema as well as checked in code: the model is told
        # in two places because this is the field the whole decision rests on.
        "reason": {"type": "string"},
    },
}

SCHEDULE_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assignments", "notes", "summary"],
    "properties": {
        "assignments": {"type": "array", "items": _ASSIGNMENT_SCHEMA},
        # What the grid does not show: a slot left short, a soft rule traded
        # against another. The manager reads these beside the schedule.
        "notes": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
}


def profile_for_model(profile: dict) -> dict:
    """The complete canonical workplace profile used for scheduling.

    The profile is already the boundary. A second field list here made newly
    saved facts disappear until both contracts were updated.
    """
    return profile if isinstance(profile, dict) else {}


def profile_beside_candidates(profile: dict) -> dict:
    """The profile as the span path sends it: everything except the roster.

    `candidate_employees` already carries every employee, filtered to those
    legally available and keyed by the ids the schema accepts. Sending
    `employees` too repeated the roster verbatim -- roughly a third of the
    request on a thirty-person team. A blacklist of one key rather than a
    field list, so newly saved profile facts keep travelling.
    """
    if not isinstance(profile, dict):
        return {}
    return {key: value for key, value in profile.items() if key != "employees"}


def slot_for_model(
    slot: dict,
    index: Optional[int] = None,
    candidates: Optional[dict] = None,
) -> dict:
    shaped = {
        "shift": slot["shift_name"],
        "date": slot["slot_date"],
        "weekday": slot["weekday"],
        "start_time": slot["start_time"],
        "end_time": slot["end_time"],
        "headcount": slot["headcount"],
        "required_roles": role_list(slot.get("required_roles")),
        "requires_shift_manager": bool(slot.get("requires_shift_manager")),
        "is_on_call": slot["is_on_call"],
        "is_night": is_night(slot),
        "hours": shift_hours(slot),
    }
    if index is not None:
        shaped["id"] = slot_id(index)
        shaped["candidate_employee_ids"] = (
            (candidates or {}).get("by_slot", {}).get(slot_id(index), [])
        )
    return shaped


def closures_for_model(profile: dict, starts_on: str, ends_on: str) -> List[dict]:
    """The closure cycle, already worked out, handed over as a fact."""
    return _closures(profile, parse_date(starts_on), parse_date(ends_on))
