"""Two deterministic ways out of a placement that warns."""

from typing import List, Optional

from app.bl.placement import values
from app.bl.shared import parse_date
from app.bl.placement.context import PlacementContext, effective_rows
from app.bl.placement.tiers import Tiers

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
    nearby: bool = True,
) -> dict:
    """Who else could take this slot, and where else this person could go.

    `nearby=False` skips the second half. It audits the period once per slot
    within reach, and a caller that only wants the colleagues -- the
    replacement tab -- was paying about half of its time for a list it threw
    away.

    `employees` come in stages (`tiers.py`): the same role from this post,
    the same role from another, then anyone else -- and inside each stage
    lightest week first, `audit.fairness()`'s arithmetic applied to a
    choice. `slots` are ordered by distance from the
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
        "slots": nearby_slots(context, employee, shift_name, slot_date) if nearby else [],
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
    tiers = Tiers(context.schedule, context.profile, employee, shift_name)
    # Ranked before checking: the order (stage, hours, name) needs no audit,
    # so the placement check -- two audits each -- runs only until the cap
    # is reached instead of once for every soldier on the roster.
    ranked = sorted(
        (
            tiers.mark({"employee": name, "hours": load.get(name, 0.0)})
            for name in _names(context)
            if name != employee and name not in taken
        ),
        key=lambda item: (item["tier"], item["hours"], item["employee"]),
    )
    options = []
    for option in ranked:
        name = option["employee"]
        if not values.is_eligible(context.profile, name, shift_name, slot_date):
            continue
        if not context.clean(name, shift_name, slot_date):
            continue
        # Said in Hebrew here rather than assembled in the browser: the
        # product's copy is Hebrew data throughout.
        option["why"] = "%s פנוי/ה ומוגדר/ת למשמרת (%s שעות בתקופה)." % (
            name, values.pretty(option["hours"])
        )
        options.append(option)
        if len(options) == _MAX_ALTERNATIVES:
            break
    return options


def _names(context: PlacementContext) -> List[str]:
    names = (values.text(person.get("name")) for person in context.employees)
    return list(dict.fromkeys(name for name in names if name))


def nearby_slots(
    context: PlacementContext, employee: str, shift_name: str, slot_date: str,
) -> List[dict]:
    """Slots near the intended date this same person could fill cleanly."""
    wanted = parse_date(slot_date)
    if wanted is None:
        return []
    options = []
    for slot in context.slots:
        name, date = values.text(slot.get("shift_name")), values.iso(slot.get("slot_date"))
        day = parse_date(date) if name and date else None
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
