"""Per-person reports: one person's totals, the team's fairness, past load.

Here rather than elsewhere in `bl/` for one reason: they must reuse
`roster.shift_hours`, the same weighted arithmetic the warnings are computed
from. An employee reading 38 where their manager reads 41 is worse than
showing nothing at all. Reports, never rules -- nothing here decides.
"""

from typing import Dict, List, Optional

from app.bl.audit.roster import index_shifts, iso_week, rows_of
from app.bl.audit.values import person_name, text
from app.bl.shared.hebrew_calendar import hebrew_weekday

# Friday and Saturday: the Israeli weekend, matching how the interview
# collects a shift's `days` and how the real files are written.
_WEEKEND_WEEKDAYS = frozenset({4, 5})


def _roster_names(employees: Optional[List[dict]]) -> List[str]:
    return [name for name in (person_name(item) for item in employees or []) if name]


def personal_summary(
    employee: str,
    assignments: List[dict],
    shifts: List[dict],
    warnings: Optional[List[dict]] = None,
    availability: Optional[List[dict]] = None,
) -> dict:
    """One person's own totals: hours, shifts, and the warnings about them.

    The on-call split is broken out because it is the number that surprises
    people: an eight-hour on-call weighted at 0.5 counts as four, which looks
    like a mistake unless the breakdown says so plainly (D9/D14).
    """
    name = text(employee)
    rows = [row for row in rows_of(assignments, index_shifts(shifts)) if row["employee"] == name]
    rows.sort(key=lambda row: (row["date"], row["shift"]))
    total = round(sum(row["hours"] for row in rows), 2)
    on_call = [row for row in rows if row["is_on_call"]]
    on_call_hours = round(sum(row["hours"] for row in on_call), 2)
    return {
        "employee": name,
        "total_hours": total,
        "shift_count": len(rows),
        "days_worked": len(set(row["date"] for row in rows)),
        "on_call_count": len(on_call),
        "on_call_hours": on_call_hours,
        "worked_hours": round(total - on_call_hours, 2),
        "by_shift": _hours_by_shift(rows),
        "by_week": _hours_by_week(rows),
        "shifts": [
            {
                "date": row["date"],
                "shift": row["shift"],
                "hours": row["hours"],
                "is_on_call": row["is_on_call"],
                "weekday": hebrew_weekday(row["day"]),
            }
            for row in rows
        ],
        # Only the warnings naming this person. A team-wide warning carries no
        # employee and is the manager's problem, not something to read as
        # being about them.
        "warnings": [
            item for item in warnings or [] if text(item.get("employee")) == name
        ],
        "constraints": [
            item for item in availability or [] if text(item.get("employee")) == name
        ],
    }


def _hours_by_shift(rows: List[dict]) -> List[dict]:
    by_shift: Dict[str, dict] = {}
    for row in rows:
        entry = by_shift.setdefault(
            row["shift"], {"shift": row["shift"], "count": 0, "hours": 0.0}
        )
        entry["count"] += 1
        entry["hours"] = round(entry["hours"] + row["hours"], 2)
    return sorted(by_shift.values(), key=lambda item: item["shift"])


def _hours_by_week(rows: List[dict]) -> List[dict]:
    weeks: Dict[str, float] = {}
    for row in rows:
        if row["day"] is None:
            continue
        key = "%d-W%02d" % iso_week(row["day"])
        weeks[key] = round(weeks.get(key, 0.0) + row["hours"], 2)
    return [{"week": key, "hours": weeks[key]} for key in sorted(weeks)]


def fairness(
    assignments: List[dict], shifts: List[dict], employees: List[dict]
) -> dict:
    """Hours per person against the team average.

    The number that answers "why is it always me". Everyone on the roster
    appears, including people with no shifts -- dropping them would hide the
    most significant case the comparison exists to reveal.
    """
    totals: Dict[str, float] = {name: 0.0 for name in _roster_names(employees)}
    for row in rows_of(assignments, index_shifts(shifts)):
        totals[row["employee"]] = round(
            totals.get(row["employee"], 0.0) + row["hours"], 2
        )
    values = list(totals.values())
    average = round(sum(values) / len(values), 2) if values else 0.0
    return {
        "average_hours": average,
        "people": sorted(
            [
                {"employee": name, "hours": hours, "delta": round(hours - average, 2)}
                for name, hours in totals.items()
            ],
            key=lambda item: (-item["hours"], item["employee"]),
        ),
    }


def load_history(
    assignments: List[dict], shifts: List[dict], employees: List[dict],
) -> List[dict]:
    """How much each person has carried across *past* periods.

    The other side of `fairness()`: this looks backwards, at who has been
    taking the nights and the weekends, and is what the scheduler reasons from
    when it decides whose turn the next one is. Counting is the one thing D3
    puts on this side of the line -- the model receives the tally, not the
    rows. Everyone on the roster appears, zeros included.
    """
    shift_index = index_shifts(shifts)
    totals: Dict[str, dict] = {name: _empty_load() for name in _roster_names(employees)}
    for row in rows_of(assignments, shift_index):
        # A name the roster no longer lists is kept: dropping it would
        # understate how much of the load the people still here carried.
        entry = totals.setdefault(row["employee"], _empty_load())
        entry["shifts"] += 1
        entry["hours"] = round(entry["hours"] + row["hours"], 2)
        if row["is_on_call"] or _is_night(shift_index.get(row["shift"])):
            entry["nights"] += 1
        if row["day"] is not None and row["day"].weekday() in _WEEKEND_WEEKDAYS:
            entry["weekends"] += 1
        if row["date"] > entry["last_worked"]:
            entry["last_worked"] = row["date"]
    return sorted(
        [dict(counts, employee=name) for name, counts in totals.items()],
        key=lambda item: (-item["nights"], -item["hours"], item["employee"]),
    )


def _is_night(shift: Optional[dict]) -> bool:
    """Whether the vocabulary marks this shift as a night.

    Read off the shift definition, never inferred from its name or start time
    (D9). A workplace that never flags a night honestly reports zero.
    """
    if not isinstance(shift, dict):
        return False
    return bool(shift.get("is_night") or shift.get("is_overnight"))


def _empty_load() -> dict:
    return {"shifts": 0, "hours": 0.0, "nights": 0, "weekends": 0, "last_worked": ""}
