"""How full a slot is has exactly one answer, and this module owns it.

`required_headcount()` says how many people a slot asks for -- the stored grid
first, the profile as fallback -- and `counts_toward_staffing()` says whether
the person standing on it fills one of those seats. The audit, the charts,
`tools.coverage_gaps` and `simulate` all go through the pair; a second count
anywhere is how a coverage bar reads 100% directly above a warning saying the
cell is short.
"""

import datetime
from typing import Dict, Iterator, List, Optional

from app.bl.audit.roster import index_people
from app.bl.audit.values import slot_date, text
from app.bl.shared.hebrew_calendar import hebrew_weekday, runs_on


def counts_toward_staffing(person: Optional[dict], profile: Optional[dict]) -> bool:
    """Whether this person fills one of a slot's seats.

    The one definition of what a shadow shift *is*. Three sources, in order:
    the person's explicit `counts_toward_staffing` wins outright; failing
    that only a trainee is in question; and a workplace-wide
    `training_policy.counts_toward_staffing` settles the trainees nobody
    ruled on individually.
    """
    person = person if isinstance(person, dict) else {}
    explicit = person.get("counts_toward_staffing")
    if isinstance(explicit, bool):
        return explicit
    if not person.get("is_trainee"):
        return True
    training = (profile or {}).get("training_policy")
    return bool(
        training.get("counts_toward_staffing") if isinstance(training, dict)
        else False
    )


def counted_rows(
    rows: List[dict], employees: List[dict], profile: dict
) -> List[dict]:
    """The rows whose person fills a seat; shadow shifts left out."""
    people = index_people(employees)
    return [
        item for item in rows
        if counts_toward_staffing(people.get(item["employee"]), profile)
    ]


def seat_counts(
    rows: List[dict], employees: List[dict], profile: dict
) -> Dict[tuple, int]:
    """Filled seats per `(date, shift)`, shadow shifts excluded."""
    counts: Dict[tuple, int] = {}
    for item in counted_rows(rows, employees, profile):
        key = (item["date"], item["shift"])
        counts[key] = counts.get(key, 0) + 1
    return counts


def checked_slots(rows: List[dict], slots: Optional[List[dict]]) -> set:
    """The `(date, shift)` pairs to grade: the grid when there is one.

    Deriving them from assignments alone would skip any slot with nobody on
    it -- an entirely unstaffed shift would report nothing, the situation the
    manager most needs told about.
    """
    if not slots:
        return {(item["date"], item["shift"]) for item in rows}
    pairs = {
        (slot_date(slot), text(slot.get("shift_name")))
        for slot in slots if isinstance(slot, dict)
    }
    return {pair for pair in pairs if pair[0] and pair[1]}


def _grid_slots(
    slots: Optional[List[dict]], shift_name: str, date: str
) -> Iterator[dict]:
    for slot in slots or []:
        if not isinstance(slot, dict):
            continue
        if slot_date(slot) == date and text(slot.get("shift_name")) == shift_name:
            yield slot


def _declared(shifts: List[dict], shift_name: str) -> Optional[dict]:
    for shift in shifts or []:
        if isinstance(shift, dict) and text(shift.get("name")) == shift_name:
            return shift
    return None


def required_headcount(
    shifts: List[dict], shift_name: str, day: Optional[datetime.date],
    slots: Optional[List[dict]] = None,
) -> Optional[int]:
    """How many people this slot asks for, or None when nobody ever said.

    **The stored grid wins.** It is what `build_slots` already worked the
    number out into and, for an imported week, what the *file* said this shift
    ran with. Recomputing from today's profile is how a Friday generated to
    ten seats gets audited against the four the other days use.
    """
    date = day.isoformat() if day else ""
    for slot in _grid_slots(slots, shift_name, date):
        headcount = slot.get("headcount")
        if isinstance(headcount, int) and not isinstance(headcount, bool):
            return headcount
    shift = _declared(shifts, shift_name)
    if shift is None or not isinstance(shift.get("staffing"), list):
        return None
    return _staffing_value(shift, day, _group_headcount)


def required_roles(
    shifts: List[dict], shift_name: str, day: Optional[datetime.date],
    slots: Optional[List[dict]] = None,
) -> List[str]:
    """Required roles copied onto the slot, with profile fallback."""
    date = day.isoformat() if day else ""
    for slot in _grid_slots(slots, shift_name, date):
        roles = slot.get("required_roles")
        if isinstance(roles, list):
            return [text(role) for role in roles if text(role)]
    shift = _declared(shifts, shift_name)
    if shift is None:
        return []
    return _staffing_value(shift, day, _group_roles) or []


def requires_shift_manager(
    shifts: List[dict], shift_name: str, date: str,
    slots: Optional[List[dict]] = None,
) -> bool:
    for slot in _grid_slots(slots, shift_name, date):
        return bool(slot.get("requires_shift_manager"))
    shift = _declared(shifts, shift_name)
    return bool(shift and shift.get("requires_shift_manager"))


def _staffing_value(shift: dict, day: Optional[datetime.date], read):
    """The per-weekday staffing group's value, or the no-days default.

    Weekdays are normalised on both sides: the interview collects `שישי` and
    `יום שישי` as the same day, and comparing raw strings once graded a
    ten-person Friday against the weekday default.
    """
    weekday = hebrew_weekday(day)
    fallback = None
    for group in shift.get("staffing") or []:
        if not isinstance(group, dict):
            continue
        value = read(group)
        if value is _SKIP:
            continue
        days = group.get("days")
        if not isinstance(days, list) or not days:
            fallback = value
        elif weekday and runs_on(days, weekday):
            return value
    return fallback


_SKIP = object()


def _group_headcount(group: dict):
    headcount = group.get("headcount")
    if not isinstance(headcount, int) or isinstance(headcount, bool):
        return _SKIP
    return headcount


def _group_roles(group: dict):
    roles = group.get("required_roles")
    if not isinstance(roles, list):
        return []
    return [text(role) for role in roles if text(role)]
