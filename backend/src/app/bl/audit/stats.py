"""`shift_stats`: the period in numbers -- coverage, load, distribution.

The manager's counterpart to `personal_summary`, reusing the same hours and
the same seat count, so a chart can never contradict the warning printed under
it. Still a report and still no authority (D3): nothing here is a target, a
quota, or a threshold the schedule is graded against.
"""

from typing import Dict, List, Optional

from app.bl.audit.codes import SEVERITY_NOTICE, severity_rank
from app.bl.audit.constraints import constraint_conflicts
from app.bl.audit.roster import index_shifts, rows_of
from app.bl.audit.staffing_rules import checked_slots, required_headcount, seat_counts
from app.bl.audit.values import parse_date, person_name, slot_date, text
from app.bl.shared.hebrew_calendar import hebrew_weekday


def shift_stats(
    assignments: List[dict],
    shifts: List[dict],
    employees: List[dict],
    slots: Optional[List[dict]] = None,
    warnings: Optional[List[dict]] = None,
    availability: Optional[List[dict]] = None,
    profile: Optional[dict] = None,
) -> dict:
    """Everyone on the roster appears in `by_employee`, zeros included."""
    shift_index = index_shifts(shifts)
    rows = rows_of(assignments, shift_index)
    return {
        "total_hours": round(sum(row["hours"] for row in rows), 2),
        "total_shifts": len(rows),
        "people_working": len(set(row["employee"] for row in rows)),
        "coverage": coverage(rows, shifts or [], slots, employees or [], profile or {}),
        "by_shift": _by_shift(rows, shift_index),
        "by_day": _by_day(rows, slots),
        "by_employee": _by_employee(rows, employees or []),
        "warning_counts": _warning_counts(warnings or []),
        "constraint_pressure": _constraint_pressure(rows, availability or []),
    }


def coverage(
    rows: List[dict], shifts: List[dict], slots: Optional[List[dict]],
    employees: Optional[List[dict]] = None, profile: Optional[dict] = None,
) -> dict:
    """Filled seats against required seats, over the period's grid.

    Counted in *seats*, not slots: two of three is two thirds covered. Slots
    whose headcount nobody stated are left out of both halves rather than
    assumed to need one -- an invented denominator makes the percentage
    fiction.
    """
    filled = seat_counts(rows, employees or [], profile or {})
    pairs = checked_slots(rows, slots) if slots else set(filled)
    required = assigned = unfilled = 0
    for date, shift_name in pairs:
        needed = required_headcount(shifts, shift_name, parse_date(date), slots)
        if needed is None:
            continue
        count = filled.get((date, shift_name), 0)
        required += needed
        assigned += min(count, needed)
        unfilled += count < needed
    return {
        "required": required,
        "assigned": assigned,
        "unfilled_slots": unfilled,
        # "0 filled of 0" is 100% covered, not an error.
        "percent": round(assigned / required * 100, 1) if required else 100.0,
    }


def _by_shift(rows: List[dict], shift_index: Dict[str, dict]) -> List[dict]:
    """Load per shift name. Every declared shift appears, staffed or not."""
    totals: Dict[str, dict] = {
        name: {"shift": name, "count": 0, "hours": 0.0,
               "is_on_call": bool(shift.get("is_on_call"))}
        for name, shift in shift_index.items()
    }
    for row in rows:
        entry = totals.setdefault(row["shift"], {
            "shift": row["shift"], "count": 0, "hours": 0.0,
            "is_on_call": row["is_on_call"],
        })
        entry["count"] += 1
        entry["hours"] = round(entry["hours"] + row["hours"], 2)
    return sorted(totals.values(), key=lambda item: item["shift"])


def _by_day(rows: List[dict], slots: Optional[List[dict]]) -> List[dict]:
    """Headcount and hours per date; grid dates nobody worked show as zero."""
    days: Dict[str, dict] = {}

    def entry(date: str) -> dict:
        return days.setdefault(date, {
            "date": date, "weekday": hebrew_weekday(parse_date(date)),
            "count": 0, "hours": 0.0, "on_call": 0,
        })

    for slot in slots or []:
        if isinstance(slot, dict) and slot_date(slot):
            entry(slot_date(slot))
    for row in rows:
        item = entry(row["date"])
        item["count"] += 1
        item["hours"] = round(item["hours"] + row["hours"], 2)
        item["on_call"] += bool(row["is_on_call"])
    return [days[key] for key in sorted(days)]


def _by_employee(rows: List[dict], employees: List[dict]) -> List[dict]:
    """Per-person load, heaviest first, everyone on the roster present."""
    totals: Dict[str, dict] = {}

    def entry(name: str) -> dict:
        return totals.setdefault(name, {
            "employee": name, "hours": 0.0, "shifts": 0, "on_call": 0, "days": 0,
        })

    for employee in employees:
        if person_name(employee):
            entry(person_name(employee))
    worked: Dict[str, set] = {}
    for row in rows:
        item = entry(row["employee"])
        item["hours"] = round(item["hours"] + row["hours"], 2)
        item["shifts"] += 1
        item["on_call"] += bool(row["is_on_call"])
        worked.setdefault(row["employee"], set()).add(row["date"])
    for name, dates in worked.items():
        totals[name]["days"] = len(dates)
    return sorted(totals.values(), key=lambda item: (-item["hours"], item["employee"]))


def _warning_counts(warnings: List[dict]) -> List[dict]:
    """How many findings of each kind -- a count, never a score."""
    counts: Dict[str, dict] = {}
    for item in warnings:
        if not isinstance(item, dict) or not text(item.get("code")):
            continue
        code = text(item.get("code"))
        entry = counts.setdefault(code, {
            "code": code,
            "severity": text(item.get("severity")) or SEVERITY_NOTICE,
            "count": 0,
        })
        entry["count"] += 1
    return sorted(
        counts.values(),
        key=lambda item: (severity_rank(item["severity"]), -item["count"], item["code"]),
    )


def _constraint_pressure(rows: List[dict], availability: List[dict]) -> dict:
    """How constrained the period was, and how often that was overridden.

    A constraint that was honored produces no warning and leaves no trace in
    the warning list -- this is the only place "how much were we working
    around?" is answerable.
    """
    blocked = conflicts = 0
    people = set()
    for item in availability:
        if not _narrows(item):
            continue
        blocked += 1
        people.add(text(item.get("employee")))
        conflicts += any(constraint_conflicts(row, item) for row in rows)
    return {
        "blocked": blocked,
        "people": len(people),
        "conflicts": conflicts,
        "honored": blocked - conflicts,
    }


def _narrows(item) -> bool:
    """Whether a constraint row narrows any choice at all.

    A positive row with no window merely says "available"; a positive time
    window ("from 16:00 onward") does narrow.
    """
    if not isinstance(item, dict):
        return False
    if not text(item.get("employee")) or not text(item.get("date")):
        return False
    return not item.get("available") or bool(
        text(item.get("start_time")) or text(item.get("end_time"))
    )
