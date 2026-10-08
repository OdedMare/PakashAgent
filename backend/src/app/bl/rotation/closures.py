"""Which closure days one person owns, and the Sunday handover."""

import datetime
from typing import List, Optional, Tuple

from app.bl.rotation.cycle import cycle, group_for_saturday
from app.bl.rotation.vocabulary import (
    CLOSURE_LEAD_DAYS, GROUPED_PATTERNS, HANDOVER_TAIL_DAYS, cycle_of_group,
    exit_pattern, minutes, saturday_of, text,
)

_WEEK = datetime.timedelta(days=7)
_DAY = datetime.timedelta(days=1)


def handover_shifts(profile: dict) -> List[str]:
    """The shift a closure is handed over on: the earliest one of the day.

    Read off the declared start times rather than matched against a name
    (D9). Ties are kept together; a workplace whose shifts carry no times
    returns nothing, and its closures end on Saturday -- no clock, no handover.
    """
    earliest, names = None, []
    for shift in (profile or {}).get("shifts") or []:
        if not isinstance(shift, dict):
            continue
        name, start = text(shift.get("name")), minutes(shift.get("start_time"))
        if not name or start is None:
            continue
        if earliest is None or start < earliest:
            earliest, names = start, [name]
        elif start == earliest and name not in names:
            names.append(name)
    return names


def closure_days(
    profile: dict, person: dict, start: datetime.date, end: datetime.date
) -> List[dict]:
    """Every closure day this person owns in the period, in date order.

    Read against *this person's own* pattern, so a תלתון א soldier and a round
    א soldier get their own weekends. Empty when the person is not on a
    rotation, the cycle is undefined, or their group does not close in this
    period -- all ordinary. The last row of a weekend is the **Sunday
    handover** (`until_handover`), the one row naming `shifts`.

    **A group is what makes a pattern rotate.** חמשושים and שושים with *no*
    group go out every Thursday or Friday, every week, and need no anchor.
    """
    pattern = exit_pattern(profile, person)
    lead = CLOSURE_LEAD_DAYS.get(pattern)
    if start > end or lead is None:
        return []
    group = text(person.get("rotation_group"))
    every_weekend = not group and pattern not in GROUPED_PATTERNS
    state, lookup = (None, "") if every_weekend else _cycle_for(profile, pattern, group)
    if not every_weekend and state is None:
        return []
    handover = handover_shifts(profile)
    rows = []
    # Walk Saturdays from the week *before* the period, so a closure starting
    # the Thursday before `start` -- or a handover on an opening Sunday --
    # still contributes its in-period days.
    saturday = saturday_of(start) - _WEEK
    while saturday - datetime.timedelta(days=6) <= end:
        owner = group if every_weekend else group_for_saturday(state, saturday)
        if owner == group:
            window = configured_window(profile, lookup, owner, saturday)
            if window:
                rows.extend(_configured_rows(profile, window, saturday, start, end, owner, pattern, lookup))
            else:
                rows.extend(_weekend_rows(
                    saturday, lead, handover, start, end, owner, pattern, lookup,
                ))
        saturday += _WEEK
    return rows


def configured_window(profile, pattern, group, saturday):
    rules = ((profile or {}).get("workplace") or {}).get("rotation_closure_windows") or []
    matching = [row for row in rules if row.get("pattern") == pattern and row.get("group") == group
                and (not row.get("starts_on") or row["starts_on"] <= saturday.isoformat())
                and (not row.get("ends_on") or row["ends_on"] >= saturday.isoformat())]
    if not matching:
        return None
    # Dated changes take precedence over the group's regular window.
    row = max(enumerate(matching), key=lambda item: (bool(item[1].get("starts_on") or item[1].get("ends_on")), item[0]))[1]
    return tuple(datetime.datetime.combine(saturday + datetime.timedelta(days=row[key + "_day"]),
                                           datetime.time.fromisoformat(row[key + "_time"]))
                 for key in ("start", "end"))


def shift_interval(day, shift):
    start, end = minutes(shift.get("start_time")), minutes(shift.get("end_time"))
    if start is None or end is None:
        return None
    midnight = datetime.datetime.combine(day, datetime.time())
    return (midnight + datetime.timedelta(minutes=start),
            midnight + datetime.timedelta(minutes=end + (1440 if end <= start else 0)))


def _configured_rows(profile, window, saturday, start, end, owner, pattern, lookup):
    rows = []
    # Include overnight shifts starting before the window opens.
    day = max(start, window[0].date() - _DAY)
    while day <= min(end, window[1].date()):
        covered, contained = [], []
        for shift in profile.get("shifts") or []:
            interval = shift_interval(day, shift)
            if interval is None:
                # A missing clock cannot bypass a configured timed closure.
                if window[0].date() <= day <= window[1].date():
                    covered.append(text(shift.get("name")))
                continue
            if interval and interval[0] < window[1] and window[0] < interval[1]:
                covered.append(text(shift.get("name")))
                if window[0] <= interval[0] and interval[1] <= window[1]:
                    contained.append(text(shift.get("name")))
        if covered:
            rows.append(dict(date=day.isoformat(), weekend=saturday.isoformat(), group=owner,
                             pattern=pattern, cycle=lookup, is_saturday=day == saturday,
                             until_handover=day > saturday, restricted_shifts=True,
                             shifts=covered, allowed_shifts=contained))
        day += _DAY
    return rows


def _cycle_for(profile: dict, pattern: str, group: str) -> Tuple[Optional[dict], str]:
    """The person's anchored cycle, or None when there is no weekend to claim.

    A span pattern carries no cycle of its own, so it is read from the group.
    `profile_service` rejects a mismatched group on save; here it is simply
    "nothing to claim".
    """
    lookup = pattern if pattern in GROUPED_PATTERNS else cycle_of_group(profile, group)
    state = cycle(profile, lookup)
    if state is None or group not in state["groups"]:
        return None, lookup
    return state, lookup


def _weekend_rows(
    saturday, lead, handover, start, end, owner, pattern, lookup,
) -> List[dict]:
    day = saturday - datetime.timedelta(days=lead)
    last = saturday + datetime.timedelta(days=HANDOVER_TAIL_DAYS if handover else 0)
    rows = []
    while day <= last:
        if start <= day <= end:
            rows.append({
                "date": day.isoformat(),
                "weekend": saturday.isoformat(),
                "group": owner,
                "pattern": pattern,
                "cycle": lookup,
                "is_saturday": day == saturday,
                # The Sunday the group is relieved on owns only the handover.
                "until_handover": day > saturday,
                "shifts": list(handover) if day > saturday else [],
            })
        day += _DAY
    return rows


def holds(profile: dict, person: dict, day: datetime.date, shift: str = "") -> bool:
    """Whether this person's own cycle holds `day`, or `shift` on it.

    `shift` matters on the Sunday handover only: the group is in for that
    morning and out for the rest of the day. Asked with no shift, a handover
    Sunday counts as held.
    """
    return any(
        not shift or shift in row.get("allowed_shifts", row["shifts"])
        or not (row["until_handover"] or row.get("restricted_shifts"))
        for row in closure_days(profile, person, day, day)
    )
