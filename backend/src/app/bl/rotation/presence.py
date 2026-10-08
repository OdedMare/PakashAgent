"""Group presence overrides and closure eligibility shared by generation and audit."""

import datetime

from app.bl.rotation.closures import closure_days, holds, shift_interval
from app.bl.rotation.vocabulary import (
    cycle_of_group, exit_pattern, groups_for, minutes, parse_date, text,
)
from app.bl.shared.hebrew_calendar import hebrew_weekday, weekday_key

_DAY = datetime.timedelta(days=1)


def _rules_on(profile, person, day, shift):
    pattern = exit_pattern(profile, person)
    group = text(person.get("rotation_group"))
    pattern = pattern if groups_for(pattern) else cycle_of_group(profile, group)
    date = day.isoformat()
    matches = [rule for rule in (profile.get("workplace") or {}).get("rotation_presence") or []
               if rule.get("pattern") == pattern and rule.get("group") == group
               and (not rule.get("starts_on") or rule["starts_on"] <= date)
               and (not rule.get("ends_on") or rule["ends_on"] >= date)
               and (not rule.get("days") or weekday_key(hebrew_weekday(day))
                    in {weekday_key(item) for item in rule["days"]})
               and (not rule.get("shifts") or shift in rule["shifts"])]
    dated = [rule for rule in matches if rule.get("starts_on") or rule.get("ends_on")]
    return dated or matches


def _window(rule, day):
    start, end = minutes(rule.get("start_time")), minutes(rule.get("end_time"))
    start = 0 if start is None else start
    end = 1440 if end is None else end
    if end <= start:
        end += 1440
    midnight = datetime.datetime.combine(day, datetime.time())
    return midnight + datetime.timedelta(minutes=start), midnight + datetime.timedelta(minutes=end)


def presence_status(profile, person, slot):
    """None leaves the cycle in charge; False blocks the whole assignment.

    Dated rules replace recurring rules. Absence always wins over presence;
    adjacent presence windows cover a continuous stay across midnight.
    """
    day = parse_date(slot["slot_date"])
    if day is None:
        return None
    interval = shift_interval(day, slot)
    matches = _rules_on(profile, person, day, slot["shift_name"])
    if interval is None:
        # Missing clocks cannot make a declared absence or timed presence safe.
        if not matches:
            return None
        return all(rule["available"] and not rule.get("start_time") and not rule.get("end_time")
                   for rule in matches)
    positives = []
    for rule_day in (day - _DAY, day, day + _DAY):
        for rule in _rules_on(profile, person, rule_day, slot["shift_name"]):
            window = _window(rule, rule_day)
            overlaps = interval[0] < window[1] and window[0] < interval[1]
            if not rule["available"] and overlaps:
                return False
            if rule["available"] and (rule_day == day or overlaps):
                positives.append(window)
    if positives:
        merged = []
        for start, end in sorted(positives):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return any(start <= interval[0] and interval[1] <= end for start, end in merged)
    return None


def closure_status(profile, person, slot):
    """Each cycle owns its own windows, even when no owner is rostered."""
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
