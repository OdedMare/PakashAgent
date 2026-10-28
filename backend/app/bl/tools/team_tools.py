"""Questions about the team over a range of dates: who works, who carried the
most, who is away, and who can shadow whom.

The questions a manager asks most are counts and filters over the stored
schedule. Answered by a model reading the whole period, they are arithmetic
by generation over thousands of rows; here they are sorted and filtered in
code, and the model only words the answer (D3).
"""

import datetime
from typing import Dict, List, Optional, Tuple

from app.bl.audit import counts_toward_staffing
from app.bl.audit.roster import index_shifts, rows_of
from app.bl.scheduler.availability import effective_availability
from app.bl.scheduler.slots import build_slots
from app.bl.shared import person_roles, role_qualified
from app.bl.tools.period_tools import Tool
from app.bl.tools.roster import resolve_employee
from app.bl.tools.values import employees, iso, shifts, text
from app.common.errors import AgentError

# Longest range one question may cover: a quarter is a report, more is a dump.
MAX_RANGE_DAYS = 93
MAX_TOP = 50
# Where the away list says a person is home on their cycle rather than held
# by a constraint somebody recorded.
_CYCLE_SOURCES = ("closure", "rotation", "presence")


def date_range(day: str = "", starts_on: str = "", ends_on: str = "") -> Tuple[str, str]:
    """`day` alone, or `starts_on`..`ends_on`; refused when neither is usable."""
    first = iso(starts_on) or iso(day)
    last = iso(ends_on) or first
    if not first:
        raise AgentError("צריך לציין תאריך או טווח תאריכים")
    start, end = datetime.date.fromisoformat(first), datetime.date.fromisoformat(last)
    if end < start:
        raise AgentError("תאריך הסיום מוקדם מתאריך ההתחלה")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise AgentError("הטווח ארוך מדי; אפשר לשאול על עד %d ימים" % MAX_RANGE_DAYS)
    return first, last


class _RangeTool(Tool):
    def _assignments(self, team_id: str, first: str, last: str) -> List[dict]:
        """Every stored row in the range, across however many periods hold it."""
        rows, seen = [], set()
        for period in self._reads.periods(team_id):
            if iso(period.get("starts_on")) > last or iso(period.get("ends_on")) < first:
                continue
            schedule = self._reads.schedule(team_id, schedule_id=text(period.get("id"))) or {}
            for row in schedule.get("assignments") or []:
                key = (text(row.get("employee")), iso(row.get("date")), text(row.get("shift")))
                if first <= key[1] <= last and key not in seen:
                    seen.add(key)
                    rows.append({"employee": key[0], "date": key[1], "shift": key[2]})
        return rows

    @staticmethod
    def _unknown_shift(profile: dict, shift_name: str) -> Optional[dict]:
        names = [text(row.get("name")) for row in shifts(profile)]
        if shift_name and shift_name not in names:
            return {"found": False, "reason": "אין משמרת בשם הזה", "shifts": names}
        return None


class WhoWorks(_RangeTool):
    """Who is on the schedule on a date or over a range, by date and shift."""

    def __call__(self, team_id: str, day: str = "", starts_on: str = "",
                 ends_on: str = "", shift_name: str = "") -> dict:
        first, last = date_range(day, starts_on, ends_on)
        profile = self._reads.profile(team_id)
        shift_name = text(shift_name)
        unknown = self._unknown_shift(profile, shift_name)
        if unknown:
            return unknown
        rows = [row for row in self._assignments(team_id, first, last)
                if not shift_name or row["shift"] == shift_name]
        if not rows:
            return {"found": False, "starts_on": first, "ends_on": last,
                    "reason": "אין שיבוצים שמורים בטווח הזה"}
        by_date: Dict[str, Dict[str, List[str]]] = {}
        for row in rows:
            by_date.setdefault(row["date"], {}).setdefault(row["shift"], []).append(row["employee"])
        people = sorted({row["employee"] for row in rows})
        return {
            "found": True, "starts_on": first, "ends_on": last,
            "people_count": len(people), "people": people,
            "days": [
                {"date": date, "shifts": [
                    {"shift": shift, "employees": sorted(names)}
                    for shift, names in sorted(by_date[date].items())
                ]}
                for date in sorted(by_date)
            ],
        }


class WorkloadRanking(_RangeTool):
    """Who carried the most shifts in a range, already sorted.

    Narrowed by shift, by role, or to shift commanders. Everyone matching the
    filter is ranked, zeros included -- the person with nothing is the most
    useful row in a fairness question.
    """

    def __call__(self, team_id: str, day: str = "", starts_on: str = "",
                 ends_on: str = "", shift_name: str = "", role: str = "",
                 commanders_only: bool = False, top: int = 5) -> dict:
        first, last = date_range(day, starts_on, ends_on)
        profile = self._reads.profile(team_id)
        shift_name, role = text(shift_name), text(role)
        unknown = self._unknown_shift(profile, shift_name)
        if unknown:
            return unknown
        people = [person for person in employees(profile) if text(person.get("name"))
                  and (not role or role in person_roles(person))
                  and (not commanders_only or person.get("is_shift_manager"))]
        if not people:
            return {"found": False, "reason": "אין אנשי צוות שמתאימים לסינון",
                    "roles": sorted({r for p in employees(profile) for r in person_roles(p)})}
        names = {text(person["name"]) for person in people}
        rows = [row for row in rows_of(self._assignments(team_id, first, last),
                                       index_shifts(shifts(profile)))
                if row["employee"] in names and (not shift_name or row["shift"] == shift_name)]
        totals = {name: {"employee": name, "shifts": 0, "hours": 0.0, "nights": 0}
                  for name in names}
        for row in rows:
            entry = totals[row["employee"]]
            entry["shifts"] += 1
            entry["hours"] = round(entry["hours"] + row["hours"], 2)
            entry["nights"] += int(row["is_night"])
        ranked = sorted(totals.values(), key=lambda item: (-item["shifts"], -item["hours"],
                                                           item["employee"]))
        most = ranked[0]["shifts"]
        size = max(1, min(int(top or 5), MAX_TOP))
        return {
            "found": True, "starts_on": first, "ends_on": last,
            "shift_name": shift_name, "role": role, "commanders_only": bool(commanders_only),
            "considered": len(ranked), "ranking": ranked[:size],
            # Ties are named outright: "the most" is several people as often
            # as it is one, and a top-1 answer would hide the others.
            "tied_for_most": [item["employee"] for item in ranked if item["shifts"] == most],
            "least_shifts": ranked[-1]["shifts"],
            "least": [item["employee"] for item in ranked if item["shifts"] == ranked[-1]["shifts"]],
        }


class WhoIsAway(_RangeTool):
    """Who is not available on each date, and why.

    Three kinds, kept apart because the manager reacts to them differently: a
    group home on its cycle is the plan working, a duty (תורנות) is somebody
    busy elsewhere on base, and a constraint (sick, leave, a recorded
    absence) is news. Read off `effective_availability`, the same
    rows the solver and the audit use, so this list cannot disagree with
    the board about who could have been placed.
    """

    def __call__(self, team_id: str, day: str = "", starts_on: str = "",
                 ends_on: str = "") -> dict:
        first, last = date_range(day, starts_on, ends_on)
        profile = self._reads.profile(team_id)
        saved = self._reads.availability(team_id, (first, last))
        rows = effective_availability(profile, saved, first, last)
        running: Dict[str, set] = {}
        for slot in build_slots(profile, first, last):
            running.setdefault(slot["slot_date"], set()).add(slot["shift_name"])
        away: Dict[Tuple[str, str], dict] = {}
        for row in rows:
            if row.get("available") or row.get("is_hard", True) is False:
                continue
            date, name = iso(row.get("date")), text(row.get("employee"))
            if not name or not first <= date <= last:
                continue
            entry = away.setdefault((date, name), {
                "employee": name, "kinds": set(), "shifts": set(),
                "whole_day": False, "reasons": [],
            })
            cycle = text(row.get("source")) in _CYCLE_SOURCES or bool(row.get("derived_from"))
            duty = text(row.get("constraint_type")) == "duty"
            entry["kinds"].add("duty" if duty else "cycle" if cycle else "constraint")
            shift = text(row.get("shift"))
            if shift:
                entry["shifts"].add(shift)
            else:
                entry["whole_day"] = True
            reason = text(row.get("reason"))
            if reason and reason not in entry["reasons"]:
                entry["reasons"].append(reason)
        days: Dict[str, List[dict]] = {}
        for (date, name), entry in sorted(away.items()):
            whole = entry["whole_day"] or bool(running.get(date)) and running[date] <= entry["shifts"]
            days.setdefault(date, []).append({
                # A recorded absence is news even on a day the cycle also
                # sends them home, so it names the day when both apply.
                "employee": name, "whole_day": whole,
                "kind": next(kind for kind in ("constraint", "duty", "cycle") if kind in entry["kinds"]),
                "shifts": [] if whole else sorted(entry["shifts"]),
                "reasons": entry["reasons"],
            })
        return {
            "found": True, "starts_on": first, "ends_on": last,
            "days": [{"date": date, "away": days[date]} for date in sorted(days)],
        }


class ShadowPartners(Tool):
    """Who can stand beside whom while somebody learns a shift.

    For a נחפף/ת: who may train them -- their own `trainers`, else whoever
    `can_train`, else any counted member -- kept to people qualified for a
    shift the trainee can stand. For anybody else: the trainees who could
    shadow them. The same arithmetic the solver uses to seat a trainee.
    """

    def __call__(self, team_id: str, employee: str) -> dict:
        profile = self._reads.profile(team_id)
        resolved = resolve_employee(profile, employee)
        if resolved["ambiguous"]:
            return {"found": False, "reason": "יש כמה אנשים בשם הזה",
                    "matches": resolved["matches"]}
        person = resolved["person"]
        if person is None:
            return {"found": False, "reason": "אין עובד/ת בשם הזה ברשימת הצוות",
                    "roster": resolved["roster"]}
        declared = shifts(profile)
        people = [row for row in employees(profile) if text(row.get("name"))]
        staff = [row for row in people if counts_toward_staffing(row, profile)]
        name = text(person["name"])

        def stands(row: dict) -> set:
            shadow = not counts_toward_staffing(row, profile)
            return {text(shift.get("name")) for shift in declared
                    if role_qualified(row, shift, declared, shadow)}

        if not counts_toward_staffing(person, profile):
            listed = [text(item) for item in person.get("trainers") or [] if text(item)]
            pool = [row for row in staff if text(row["name"]) in listed] if listed \
                else [row for row in staff if row.get("can_train")] or staff
            mine = stands(person)
            partners = [row for row in pool if stands(row) & mine]
            return {"found": True, "employee": name, "is_trainee": True,
                    "direction": "trainers", "basis": "listed" if listed else (
                        "can_train" if any(row.get("can_train") for row in staff) else "anyone"),
                    "partners": [{"employee": text(row["name"]), "role": text(row.get("role")),
                                  "shared_shifts": sorted(stands(row) & mine)}
                                 for row in partners]}
        mine = stands(person)
        trainees = []
        for row in people:
            if counts_toward_staffing(row, profile):
                continue
            listed = [text(item) for item in row.get("trainers") or [] if text(item)]
            shared = stands(row) & mine
            if (listed and name in listed) or (not listed and shared):
                trainees.append({"employee": text(row["name"]), "role": text(row.get("role")),
                                 "shared_shifts": sorted(shared)})
        return {"found": True, "employee": name, "is_trainee": False,
                "direction": "trainees", "can_train": bool(person.get("can_train")),
                "partners": trainees}
