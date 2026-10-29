"""Day-based cycles: N days on base, M days home, per group, from one anchor.

A round or a תלתון turns on weekends. An 11/3, a 12/2 or a שבוע־שבוע turns on
*days*, and its weekends fall out of the arithmetic instead of anchoring it:
on an 11/3 anchored on a Sunday with two groups half a cycle apart, group א is
home Thursday to Saturday of its second week and group ב of its first, so each
group stays every other weekend without the cycle ever naming one.

A unit may run several of these side by side, so each is stored under its own
id in `workplace.day_cycles` and a person points at one with
`exit_pattern = "cycle:<id>"`. Nothing here is guessed: a cycle with no anchor
produces no home days, and `configuration_errors` refuses to schedule it.
"""

import datetime
from typing import Any, List, Optional, Tuple

from app.bl.rotation.vocabulary import minutes, parse_date, text

DAY_CYCLE_PREFIX = "cycle:"

_DAY = datetime.timedelta(days=1)


def is_day_cycle(pattern: str) -> bool:
    return text(pattern).startswith(DAY_CYCLE_PREFIX)


def cycle_id(pattern: str) -> str:
    return text(pattern)[len(DAY_CYCLE_PREFIX):] if is_day_cycle(pattern) else ""


def day_cycle(profile: dict, pattern: str) -> Optional[dict]:
    """The cycle `pattern` names, or None when the workplace has no such cycle."""
    wanted = cycle_id(pattern)
    if not wanted:
        return None
    workplace = (profile or {}).get("workplace") or {}
    for row in workplace.get("day_cycles") or []:
        if isinstance(row, dict) and text(row.get("id")) == wanted:
            return row
    return None


def length(cycle: dict) -> int:
    return int(cycle.get("base_days") or 0) + int(cycle.get("home_days") or 0)


def default_offset(index: int, count: int, days: int) -> int:
    """Groups spread evenly over the cycle unless the manager says otherwise."""
    return round(index * days / count) % days if count and days else 0


def offset(cycle: dict, group: str) -> Optional[int]:
    """Days after the anchor on which `group` starts its stretch on base."""
    groups = [text(item) for item in cycle.get("groups") or []]
    if group not in groups:
        return None
    stated = (cycle.get("offsets") or {}).get(group)
    if isinstance(stated, int) and not isinstance(stated, bool):
        return stated
    return default_offset(groups.index(group), len(groups), length(cycle))


TIMING_KEYS = ("leave_day", "leave_time", "return_day", "return_time")

# How far a departure or a return may move from its nominal day, either way.
MAX_DAY_SHIFT = 3


def _at(day: datetime.date, shift: Any, clock: str) -> datetime.datetime:
    moved = day + datetime.timedelta(days=shift if isinstance(shift, int) else 0)
    stated = minutes(clock)
    return datetime.datetime.combine(moved, datetime.time()) + datetime.timedelta(minutes=stated or 0)


def timing(cycle: dict, group: str, leave_day: datetime.date) -> dict:
    """When `group` leaves and returns on the stretch nominally opening `leave_day`.

    Three layers, each overriding only the fields it states: the cycle's own
    hours, then `group_times[group]`, then a dated `time_changes` row covering
    that departure -- one naming the group before one naming every group.
    """
    result = {key: cycle.get(key) for key in TIMING_KEYS}
    layers = [((cycle.get("group_times") or {}).get(group) or {})]
    date = leave_day.isoformat()
    dated = [row for row in cycle.get("time_changes") or [] if isinstance(row, dict)
             and text(row.get("group")) in ("", group)
             and (not row.get("starts_on") or row["starts_on"] <= date)
             and (not row.get("ends_on") or row["ends_on"] >= date)]
    layers += sorted(dated, key=lambda row: bool(text(row.get("group"))))
    for layer in layers:
        result.update({key: layer[key] for key in TIMING_KEYS
                       if layer.get(key) not in (None, "")})
    return result


def home_windows(
    cycle: dict, group: str, start: datetime.date, end: datetime.date,
) -> List[Tuple[datetime.datetime, datetime.datetime]]:
    """Every stretch `group` is home that touches `start`..`end`, as datetimes.

    Nominally a stretch opens at the start of its first home day and closes at
    the start of the next first base day. `timing` may move either end by a
    few days and to any hour, so a transition day is shared: before the
    departure, or after the return, the group is still on base.
    """
    anchor, days = parse_date(cycle.get("anchor_date")), length(cycle)
    shift = offset(cycle, group)
    base, home = int(cycle.get("base_days") or 0), int(cycle.get("home_days") or 0)
    if anchor is None or shift is None or days <= 0 or home <= 0 or start > end:
        return []
    first = anchor + datetime.timedelta(days=shift)
    reach = datetime.timedelta(days=MAX_DAY_SHIFT + 1)
    # Start early enough that a stretch opening before `start` still counts.
    turn = (start - reach - first).days // days - 1
    windows = []
    while True:
        cycle_start = first + datetime.timedelta(days=turn * days)
        leave_day = cycle_start + datetime.timedelta(days=base)
        if leave_day > end + reach:
            break
        when = timing(cycle, group, leave_day)
        windows.append((_at(leave_day, when["leave_day"], text(when["leave_time"])),
                        _at(cycle_start + datetime.timedelta(days=days),
                            when["return_day"], text(when["return_time"]))))
        turn += 1
    return [window for window in windows
            if window[0].date() <= end + _DAY and window[1].date() >= start]


def on_base(cycle: dict, group: str, day: datetime.date) -> bool:
    """Whether `group` spends any part of `day` on base."""
    midnight = datetime.datetime.combine(day, datetime.time())
    covered = midnight
    for opens, closes in sorted(home_windows(cycle, group, day, day)):
        if opens > covered:
            return True
        covered = max(covered, closes)
    return covered < midnight + _DAY


def status(profile: dict, person: dict, slot: dict) -> Optional[bool]:
    """False when the slot overlaps a stretch this person's group is home.

    None otherwise: being on base makes somebody available to the rest of the
    rules, not obliged to work. A slot with no clock is blocked on any day a
    home stretch touches, because a missing time cannot make an absence safe.
    """
    # Imported here: `closures` reaches this module through `cycle`.
    from app.bl.rotation.closures import shift_interval

    cycle = day_cycle(profile, text(person.get("exit_pattern")))
    group = text(person.get("rotation_group"))
    day = parse_date(slot.get("slot_date"))
    if cycle is None or day is None:
        return None
    interval = shift_interval(day, slot)
    if interval is None:
        midnight = datetime.datetime.combine(day, datetime.time())
        interval = (midnight, midnight + _DAY)
    for opens, closes in home_windows(cycle, group, day - _DAY, day + _DAY):
        if interval[0] < closes and opens < interval[1]:
            return False
    return None


def label(cycle: Optional[dict], group: str) -> str:
    name = text((cycle or {}).get("name")) or "מחזור"
    return "%s %s" % (name, group) if text(group) else name


def configuration_errors(profile: dict, person: dict) -> List[str]:
    """What stops this person's day cycle from being scheduled."""
    name, group = text(person.get("name")), text(person.get("rotation_group"))
    cycle = day_cycle(profile, text(person.get("exit_pattern")))
    if cycle is None:
        return ["מחזור היציאות של %s אינו מוגדר ביחידה" % name]
    if group not in [text(item) for item in cycle.get("groups") or []]:
        return ["הקבוצה של %s אינה שייכת ל%s" % (name, label(cycle, ""))]
    if parse_date(cycle.get("anchor_date")) is None:
        return ["לא הוגדר עוגן ל%s (היום שבו קבוצה %s נכנסת לבסיס)"
                % (label(cycle, ""), text((cycle.get("groups") or [""])[0]))]
    return []
