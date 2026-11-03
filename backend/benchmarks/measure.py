"""What one solve achieved, as numbers two runs can be compared on.

Read from the solver's answer and the scenario's own inputs, never from the
solver's internal prices: a change to a weight must show up here as better
or worse schedules, not as a different objective in different units.

| measure | lower is better? | what it is |
|---|---|---|
| `unfilled_seats` | yes | seats the slot grid asked for and nobody filled |
| `missing_roles` | yes | audit warnings for a required role or shift manager absent |
| `warnings` | yes | every audit warning on the result |
| `soft_absences_broken` | yes | soft "rather not" days the person was placed on anyway |
| `prefers_met_pct` | no | `prefer` requests the schedule honours |
| `soft_avoids_broken` | yes | placements on a shift the person asked to avoid |
| `shift_spread` / `night_spread` | yes | most minus fewest shifts (nights) among counted staff |
| `shifts_stddev` | yes | standard deviation of shifts per counted person |
| `short_rests` | yes | pairs of one person's shifts less than 16 hours apart |
| `min_rest_hours` | no | the shortest rest anyone gets |
| `gap_pct` | yes | how far the answer may be from optimal, by the solver's own bound |
| `wall_ms` | yes | the solve's time, both phases |
"""

import datetime
from statistics import pstdev
from typing import Dict, List

from app.bl.audit import codes, counts_toward_staffing
from app.bl.audit.roster import is_night
from app.bl.schedule_requests import covers, read_requests
from app.bl.scheduler.quality import quality

SHORT_REST_HOURS = 16
_ROLE_CODES = (codes.MISSING_ROLE, codes.MISSING_COMMANDER)


def measure(scenario, result: dict) -> dict:
    profile, rows = scenario.profile, result["assignments"]
    metrics = result["metrics"]
    graded = quality(rows, result["slots"], profile, result["warnings"])
    loads = _loads(profile, rows)
    rests = _rests(profile, rows)
    return {
        "scenario": scenario.name,
        "status": metrics.get("solver_status"),
        "unfilled_seats": graded["unfilled_seats"],
        "missing_roles": sum(item["count"] for item in graded["warning_counts"]
                             if item["code"] in _ROLE_CODES),
        "warnings": len(result["warnings"]),
        "soft_absences_broken": _soft_absences_broken(scenario, rows),
        "prefers_met_pct": _prefers_met(scenario, rows),
        "soft_avoids_broken": _soft_avoids_broken(scenario, rows),
        "shift_spread": _spread(loads["shifts"]),
        "night_spread": _spread(loads["nights"]),
        "shifts_stddev": round(pstdev(loads["shifts"].values()), 2) if loads["shifts"] else 0.0,
        "short_rests": sum(1 for gap in rests if gap < SHORT_REST_HOURS),
        "min_rest_hours": round(min(rests), 1) if rests else None,
        "objective": metrics.get("objective"),
        "gap_pct": metrics.get("gap_pct"),
        "wall_ms": metrics.get("solver_ms"),
        "phases": metrics.get("phases"),
    }


def _loads(profile: dict, rows: List[dict]) -> Dict[str, Dict[str, int]]:
    shifts = {shift["name"]: shift for shift in profile.get("shifts") or []}
    staff = [person["name"] for person in profile.get("employees") or []
             if counts_toward_staffing(person, profile)]
    loads = {"shifts": dict.fromkeys(staff, 0), "nights": dict.fromkeys(staff, 0)}
    for row in rows:
        if row["employee"] in loads["shifts"]:
            loads["shifts"][row["employee"]] += 1
            loads["nights"][row["employee"]] += int(is_night(shifts.get(row["shift"], {})))
    return loads


def _spread(load: Dict[str, int]) -> int:
    return max(load.values()) - min(load.values()) if load else 0


def _rests(profile: dict, rows: List[dict]) -> List[float]:
    """Hours between each person's consecutive clocked shifts."""
    shifts = {shift["name"]: shift for shift in profile.get("shifts") or []}
    spans: Dict[str, list] = {}
    for row in rows:
        shift = shifts.get(row["shift"]) or {}
        if not shift.get("start_time") or not shift.get("end_time"):
            continue
        day = datetime.date.fromisoformat(row["date"])
        begins = datetime.datetime.combine(day, datetime.time.fromisoformat(shift["start_time"]))
        ends = datetime.datetime.combine(day, datetime.time.fromisoformat(shift["end_time"]))
        if ends <= begins:
            ends += datetime.timedelta(days=1)
        spans.setdefault(row["employee"], []).append((begins, ends))
    gaps = []
    for items in spans.values():
        items.sort()
        gaps += [(later[0] - earlier[1]).total_seconds() / 3600.0
                 for earlier, later in zip(items, items[1:])]
    return gaps


def _soft_absences_broken(scenario, rows: List[dict]) -> int:
    soft = {(item["employee"], item["date"]) for item in scenario.availability
            if item.get("is_hard") is False}
    return sum(1 for row in rows if (row["employee"], row["date"]) in soft)


def _requests(scenario, kind: str) -> List[dict]:
    requests, _ = read_requests(scenario.requests, scenario.profile)
    return [item for item in requests if item["kind"] == kind and not item["is_hard"]]


def _prefers_met(scenario, rows: List[dict]):
    wishes = _requests(scenario, "prefer")
    if not wishes:
        return None
    met = sum(1 for wish in wishes if any(
        row["employee"] in wish["employees"] and covers(wish, row["shift"], row["date"])
        for row in rows))
    return round(100.0 * met / len(wishes), 1)


def _soft_avoids_broken(scenario, rows: List[dict]) -> int:
    avoids = _requests(scenario, "avoid")
    return sum(1 for row in rows for wish in avoids
               if row["employee"] in wish["employees"] and covers(wish, row["shift"], row["date"]))
