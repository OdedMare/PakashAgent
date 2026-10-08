"""Group presence overrides and per-cycle closure eligibility shared by all writers."""

import datetime

from app.bl.rotation.closures import closure_days, holds
from app.bl.rotation.vocabulary import cycle_of_group, exit_pattern, groups_for, parse_date, text
from app.bl.shared.hebrew_calendar import hebrew_weekday, weekday_key


def presence_status(profile, person, slot):
    """None leaves the cycle in charge; False always blocks the whole assignment."""
    from app.bl.audit.constraints import constraint_conflicts

    pattern = exit_pattern(profile, person)
    pattern = pattern if groups_for(pattern) else cycle_of_group(profile, text(person.get("rotation_group")))
    date, shift = slot["slot_date"], slot["shift_name"]
    day = parse_date(date)
    if day is None:
        return None
    matches = [rule for rule in (profile.get("workplace") or {}).get("rotation_presence") or []
               if rule.get("pattern") == pattern and rule.get("group") == person.get("rotation_group")
               and (not rule.get("starts_on") or rule["starts_on"] <= date)
               and (not rule.get("ends_on") or rule["ends_on"] >= date)
               and (not rule.get("days") or weekday_key(hebrew_weekday(day))
                    in {weekday_key(day) for day in rule["days"]})
               and (not rule.get("shifts") or shift in rule["shifts"])]
    if not matches:
        return None
    dated = [rule for rule in matches if rule.get("starts_on") or rule.get("ends_on")]
    matches = dated or matches
    occurrence = dict(employee="group", date=date, shift=shift,
                      start_time=slot.get("start_time"), end_time=slot.get("end_time"))
    if any(constraint_conflicts(occurrence, dict(rule, employee="group", date=date, shift=shift))
           for rule in matches):
        return False
    return True if any(rule["available"] for rule in matches) else None


def closure_status(profile, person, slot):
    """Each cycle owns only its own windows, even when no owner is rostered."""
    pattern = exit_pattern(profile, person)
    group = text(person.get("rotation_group"))
    if not group:
        return None
    lookup = pattern if groups_for(pattern) else cycle_of_group(profile, group)
    day = parse_date(slot["slot_date"])
    if day is None:
        return None
    claims = []
    for owner in groups_for(lookup) or ():
        probe = dict(exit_pattern=lookup, rotation_group=owner)
        for row in closure_days(profile, probe, day, day):
            if (row["until_handover"] or row.get("restricted_shifts")) and slot["shift_name"] not in row["shifts"]:
                continue
            claims.append(owner == group and holds(profile, person, day, slot["shift_name"]))
    return all(claims) if claims else None
