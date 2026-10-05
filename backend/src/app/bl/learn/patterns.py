"""Patterns in uploaded schedule files, counted. No model call.

"יערה worked 14 of the last 16 mornings and no evenings" is arithmetic over
the imported assignments, and arithmetic is code's job (D3). A pattern is
evidence about the world, not a rule: a file showing nobody on Saturday may
mean Saturday is closed, or that the sheet only covered weekdays.
"""

from typing import Any, Dict, List, Optional

from app.bl.hebrew_calendar import HEBREW_WEEKDAYS, hebrew_weekday
from app.bl.learn.values import bounded_rows, date_of, text

# A person must appear this many times before their record is read as a
# pattern at all; a confident claim from three shifts loses the manager's
# trust on the first screen.
_MIN_OBSERVATIONS = 4
# How lopsided a split has to be before it is worth mentioning. 0.9 rather
# than 1.0 because a real rota has exceptions.
_DOMINANT = 0.9
# The mirror: a shift someone has essentially never worked.
_ABSENT = 0.02


def observe(
    assignments: List[dict],
    unavailability: Optional[List[dict]] = None,
    profile: Optional[dict] = None,
) -> dict:
    """Countable facts across every imported period.

    Per-person tallies, the shift and weekday splits, the coverage of the
    history itself, and the constraints the files stated outright.
    """
    rows = bounded_rows(assignments)
    people = _tally_people(rows)
    return {
        "periods": _period(rows),
        "people": _per_person(people, _declared_shifts(profile)),
        "coverage": _coverage(rows),
        "stated_unavailability": _stated(unavailability),
        "totals": {
            "assignments": len(rows),
            "people": len(people),
            "shifts": sorted({text(row.get("shift")) for row in rows if text(row.get("shift"))}),
        },
    }


def _tally_people(rows: List[dict]) -> Dict[str, Dict[str, Any]]:
    people: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name, shift_name, date = text(row.get("employee")), text(row.get("shift")), date_of(row.get("date"))
        if not name or not date:
            continue
        record = people.setdefault(name, {
            "total": 0, "shifts": {}, "weekdays": {},
            "first_seen": date, "last_seen": date,
        })
        weekday = hebrew_weekday(date)
        record["total"] += 1
        record["shifts"][shift_name] = record["shifts"].get(shift_name, 0) + 1
        record["weekdays"][weekday] = record["weekdays"].get(weekday, 0) + 1
        record["first_seen"] = min(record["first_seen"], date)
        record["last_seen"] = max(record["last_seen"], date)
    return people


def _per_person(people: Dict[str, Dict[str, Any]], shifts: List[str]) -> List[dict]:
    """Each person's record, with the lopsided splits already identified.

    The dominance test runs here rather than in the prompt because which side
    of a threshold a ratio falls on is arithmetic. `shifts` is the declared
    vocabulary, so a shift never worked shows as a zero -- the absence is the
    whole signal.
    """
    found = []
    for name in sorted(people):
        record = people[name]
        total = record["total"]
        always, never = [], []
        if total >= _MIN_OBSERVATIONS:
            for shift_name in shifts or list(record["shifts"]):
                share = float(record["shifts"].get(shift_name, 0)) / total
                if share >= _DOMINANT:
                    always.append(shift_name)
                elif share <= _ABSENT:
                    never.append(shift_name)
        found.append({
            "employee": name,
            "assignments": total,
            "by_shift": record["shifts"],
            "by_weekday": record["weekdays"],
            "always": always,
            "never": never,
            "first_seen": record["first_seen"].isoformat(),
            "last_seen": record["last_seen"].isoformat(),
            # Below the floor nothing is claimed, and the reason is stated.
            "enough_data": total >= _MIN_OBSERVATIONS,
        })
    return found


def _coverage(rows: List[dict]) -> dict:
    """Which weekdays and shifts the history covers at all.

    A weekday with no rows anywhere may be a closed day or merely a day the
    sheets never included -- opposite meanings, reported as a fact.
    """
    weekdays: Dict[str, int] = {}
    per_shift: Dict[str, int] = {}
    for row in rows:
        date = date_of(row.get("date"))
        if date is None:
            continue
        weekday = hebrew_weekday(date)
        weekdays[weekday] = weekdays.get(weekday, 0) + 1
        shift_name = text(row.get("shift"))
        if shift_name:
            per_shift[shift_name] = per_shift.get(shift_name, 0) + 1
    return {
        "by_weekday": weekdays,
        "by_shift": per_shift,
        "weekdays_never_seen": [day for day in HEBREW_WEEKDAYS if day not in weekdays],
    }


def _stated(unavailability: Optional[List[dict]]) -> List[dict]:
    """Constraints the files stated outright, which are not inferences.

    A `לא זמינה` cell is evidence of a completely different quality from a
    counted absence, so it travels separately and is never blended in.
    """
    return [
        {
            "employee": text(row.get("employee")),
            "date": date_of(row.get("date")).isoformat(),
            "shift": text(row.get("shift")),
            "reason": text(row.get("reason")),
        }
        for row in bounded_rows(unavailability) if date_of(row.get("date"))
    ]


def _period(rows: List[dict]) -> dict:
    dates = sorted(day for day in (date_of(row.get("date")) for row in rows) if day is not None)
    if not dates:
        return {"starts_on": "", "ends_on": "", "days": 0}
    return {
        "starts_on": dates[0].isoformat(),
        "ends_on": dates[-1].isoformat(),
        "days": (dates[-1] - dates[0]).days + 1,
    }


def _declared_shifts(profile: Optional[dict]) -> List[str]:
    names = []
    for shift in (profile or {}).get("shifts") or []:
        name = text(shift.get("name")) if isinstance(shift, dict) else text(shift)
        if name and name not in names:
            names.append(name)
    return names
