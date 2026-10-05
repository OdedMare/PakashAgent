"""The manual picker's roster, and whose closure a slot falls in."""

from typing import List, Optional

from app.bl import rotation
from app.bl.placement import values
from app.bl.placement.context import PlacementContext, effective_rows

# What "the rotation says nothing about this slot" looks like on the wire. A
# shape rather than a null so the client renders one branch.
_NO_CLOSURE = {
    "date": "", "groups": [], "label": "", "employees": [],
    "until_handover": False,
}


def closure_of(profile: dict, slot_date: str, shift_name: str = "") -> dict:
    """Whose closure this slot falls in, for the dialog to say so.

    The rotation is the one fact about a placement the manager cannot read
    off the grid. Empty on an ordinary date, on an unanchored cycle, and past
    the Sunday handover -- all "the rotation has nothing to say here".
    """
    day = values.parse(values.iso(slot_date))
    if day is None:
        return _NO_CLOSURE
    found = rotation.by_date(profile, day, day).get(day.isoformat())
    if not found:
        return _NO_CLOSURE
    if found["until_handover"] and values.text(shift_name) not in found["shifts"]:
        return _NO_CLOSURE
    return {
        key: found[key]
        for key in ("date", "groups", "label", "employees", "until_handover")
    }


def employee_options(
    schedule: dict,
    profile: dict,
    shift_name: str,
    slot_date: str,
    availability: Optional[List[dict]] = None,
    moving_assignment_id: str = "",
) -> List[dict]:
    """Every roster member for a manual picker, with a concrete why-not.

    Each option carries the person's rotation and whether they are the ones
    *in* on this slot: "who is free" and "whose weekend is it" are different
    questions, so closers sort to the top of a closure slot, ahead of the
    fairness ordering that governs an ordinary day.
    """
    shift_name, slot_date = values.text(shift_name), values.iso(slot_date)
    context = PlacementContext(
        schedule, profile,
        effective_rows(schedule, profile, availability, slot_date),
        moving_assignment_id,
    )
    load = values.hours_by_employee(schedule, profile)
    day = values.parse(slot_date)
    options = [
        _option(context, person, shift_name, slot_date, day, load)
        for person in context.employees if values.text(person.get("name"))
    ]
    options.sort(key=lambda item: (
        not item["available"], not item["closing"], item["hours"], item["employee"],
    ))
    return options


def _option(context, person, shift_name, slot_date, day, load) -> dict:
    name = values.text(person.get("name"))
    verdict = context.verdict(name, shift_name, slot_date)
    return {
        "employee": name,
        "available": verdict["ok"],
        "reasons": verdict["reasons"],
        "hours": load.get(name, 0.0),
        "is_shift_manager": bool(person.get("is_shift_manager")),
        "can_train": bool(person.get("can_train")),
        "rotation": rotation.label(
            _cycle_of(context.profile, person),
            values.text(person.get("rotation_group")),
        ),
        "closing": bool(
            day is not None
            and rotation.holds(context.profile, person, day, shift_name)
        ),
    }


def _cycle_of(profile: dict, person: dict) -> str:
    """Which cycle a person turns on -- ג can only be a תלתון, so the label
    needs the cycle, not just the letter."""
    pattern = rotation.exit_pattern(profile, person)
    if pattern in ("round", "triplet"):
        return pattern
    if values.text(person.get("rotation_group")) == "ג":
        return "triplet"
    mode = values.text(((profile or {}).get("workplace") or {}).get("rotation_mode"))
    return mode if mode in ("round", "triplet") else "round"
