"""Two deterministic ways out of a placement that warns."""

from typing import List, Optional

from app.bl.placement import values
from app.bl.placement.context import PlacementContext, effective_rows

# How many alternatives are worth offering. Past a handful the list stops
# being an answer and becomes a second grid to read.
_MAX_ALTERNATIVES = 5

# How far either side of the intended date to look for a slot the same person
# could take instead. Past a week the manager is choosing a different week.
_NEARBY_DAYS = 7


def suggest_alternatives(
    schedule: dict,
    profile: dict,
    employee: str,
    shift_name: str,
    slot_date: str,
    availability: Optional[List[dict]] = None,
    moving_assignment_id: str = "",
) -> dict:
    """Who else could take this slot, and where else this person could go.

    `employees` are sorted lightest week first -- `audit.fairness()`'s
    arithmetic applied to a choice. `slots` are ordered by distance from the
    date the manager actually wanted. Both are filtered by re-checking each
    option and keeping only the clean ones.
    """
    employee, shift_name = values.text(employee), values.text(shift_name)
    slot_date = values.iso(slot_date)
    context = PlacementContext(
        schedule, profile,
        effective_rows(schedule, profile, availability, slot_date),
        moving_assignment_id,
    )
    return {
        "employees": free_employees(context, employee, shift_name, slot_date),
        "slots": nearby_slots(context, employee, shift_name, slot_date),
    }


def free_employees(
    context: PlacementContext, employee: str, shift_name: str, slot_date: str,
) -> List[dict]:
    """Colleagues who could take this slot with no warning of their own."""
    taken = {
        row["employee"]
        for row in values.rows(context.schedule, drop=context.moving)
        if row["shift"] == shift_name and row["date"] == slot_date
    }
    load = values.hours_by_employee(context.schedule, context.profile)
    options = []
    for person in context.employees:
        name = values.text(person.get("name"))
        if not name or name == employee or name in taken:
            continue
        if not values.is_eligible(context.profile, name, shift_name, slot_date):
            continue
        if not context.clean(name, shift_name, slot_date):
            continue
        options.append({
            "employee": name,
            "hours": load.get(name, 0.0),
            # Said in Hebrew here rather than assembled in the browser: the
            # product's copy is Hebrew data throughout.
            "why": "%s פנוי/ה ומוגדר/ת למשמרת (%s שעות בתקופה)." % (
                name, values.pretty(load.get(name, 0.0))
            ),
        })
    options.sort(key=lambda item: (item["hours"], item["employee"]))
    return options[:_MAX_ALTERNATIVES]


def nearby_slots(
    context: PlacementContext, employee: str, shift_name: str, slot_date: str,
) -> List[dict]:
    """Slots near the intended date this same person could fill cleanly."""
    wanted = values.parse(slot_date)
    if wanted is None:
        return []
    options = []
    for slot in context.slots:
        name, date = values.text(slot.get("shift_name")), values.iso(slot.get("slot_date"))
        day = values.parse(date) if name and date else None
        if day is None or (name == shift_name and date == slot_date):
            continue
        distance = abs((day - wanted).days)
        if distance > _NEARBY_DAYS or not context.clean(employee, name, date):
            continue
        options.append({
            "shift_name": name,
            "slot_date": date,
            "distance": distance,
            "why": "%s ב-%s פנויה עבור %s." % (name, date, employee),
        })
    options.sort(key=lambda item: (item["distance"], item["slot_date"], item["shift_name"]))
    return options[:_MAX_ALTERNATIVES]
