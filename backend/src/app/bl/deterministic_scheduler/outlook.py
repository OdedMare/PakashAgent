"""`outlook`: the load each person is already committed to in the days ahead.

A day-by-day filler balancing only what has been worked so far cannot see
that one rotation group closes the coming weekend. It spreads Sunday to
Wednesday evenly, and then the closing group carries Thursday to Saturday on
top. The outlook is each person's expected share of the seats still open
over the next days: a seat's hours split evenly among everyone who could
legally take it. On an open day that share is the same for everybody and
changes nothing; on a closing day it falls on the closers alone, so the open
days ahead of it lean towards the other group.
"""

import datetime
from typing import Dict, List

from app.bl.audit import constraint_conflicts, counts_toward_staffing
from app.bl.audit.roster import index_shifts, is_night, shift_hours
from app.bl.deterministic_scheduler.rows import assignment, eligible, same_slot, text
from app.bl.scheduler import build_slots, effective_availability

# One round week: far enough to see the next closure from any open day.
LOOKAHEAD_DAYS = 6


def outlook(profile: dict, people: Dict[str, dict], availability, day: str,
            committed: List[dict]) -> Dict[str, dict]:
    """Expected `hours` and `nights` per person over the days after `day`.

    Seats already filled by `committed` rows are left out: those rows are
    counted as worked load, and counting them again would charge twice.
    """
    first = datetime.date.fromisoformat(day) + datetime.timedelta(days=1)
    last = first + datetime.timedelta(days=LOOKAHEAD_DAYS - 1)
    result = {name: {"hours": 0.0, "nights": 0.0} for name in people}
    slots = build_slots(profile, first.isoformat(), last.isoformat())
    if not slots:
        return result
    blocking = {}
    for item in effective_availability(profile, availability, first.isoformat(), last.isoformat()):
        if isinstance(item, dict) and item.get("is_hard", True) is not False:
            blocking.setdefault(text(item.get("employee")), []).append(item)
    rows = [row for row in map(assignment, committed or []) if row]
    shifts = index_shifts((profile or {}).get("shifts") or [])
    staffing = {name: counts_toward_staffing(person, profile) for name, person in people.items()}
    for slot in slots:
        filled = sum(same_slot(row, slot) and staffing.get(row["employee"], False) for row in rows)
        open_seats = max(0, int(slot.get("headcount") or 0)) - filled
        if open_seats <= 0:
            continue
        legal = [
            name for name, person in people.items()
            if staffing[name] and eligible(person, slot["shift_name"])
            and not _blocked(name, slot, blocking.get(name, []))
        ]
        if not legal:
            continue
        shift = shifts.get(slot["shift_name"]) or {}
        share = open_seats / len(legal)
        night = is_night(shift)
        for name in legal:
            result[name]["hours"] += share * shift_hours(shift)
            result[name]["nights"] += share if night else 0.0
    return result


def _blocked(name: str, slot: dict, constraints: List[dict]) -> bool:
    candidate = {
        "employee": name, "shift": slot["shift_name"], "date": slot["slot_date"],
        "start_time": slot.get("start_time"), "end_time": slot.get("end_time"),
    }
    return any(constraint_conflicts(candidate, item) for item in constraints)
