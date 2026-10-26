"""Who should cover an absent person's shifts, spread as evenly as possible.

**No model, no write.** Candidates come from `find_replacements`, which
already keeps only people the placement checks pass. What this adds is the
*whole* absence at once: two shifts are not two independent questions,
because the person lightest before the first is not lightest after it. So
the slots are filled in date order and the load is recounted after every
pick, the same arithmetic the stats panel draws (`audit.shift_stats`), and
each pick is re-audited beside the earlier ones so two covers cannot quietly
stack into a double booking or a short rest.
"""

from typing import Dict, List, Optional

from app.bl.audit import shift_stats
from app.bl.chat_contract import GAP_CODES, audit_plan, changed_rows
from app.bl.shared import iso, warning_key
from app.bl.tools import ScheduleTools

_NO_PICK = "לא נמצא מחליף שעומד בכל הכללים בלי ליצור חריגה"


def absence_constraints(employee: str, dates: List[str], reason: str) -> List[dict]:
    """One whole-day unavailability per date, days with no shift included:
    a later build must not place them there either."""
    return [
        dict(employee=employee, date=date, shift="", available=False,
             is_hard=True, reason=reason)
        for date in dates
    ]


class AbsenceOptions:
    def __init__(self, repository, context):
        self._repo = repository
        self._context = context
        self._tools = ScheduleTools(repository)

    def build(self, team_id: str, employee: str, dates: List[str],
              chosen: Optional[List[dict]] = None, reason: str = "") -> dict:
        """The affected shifts, their ranked candidates and a fair pick each.

        `chosen` are the manager's own picks; they win over the fair one.
        One plan edits one stored period, so when the shifts sit in several
        the earliest is planned and the rest are listed in `elsewhere` --
        the absence itself is still saved for every date.
        """
        profile = self._context.profile(team_id)
        found = dict(employee=employee, dates=list(dates), schedule_id="",
                     slots=[], free_dates=list(dates), results=[], error="", elsewhere=[])
        periods = self._periods_with_shifts(team_id, employee, dates)
        if not periods:
            return found
        schedule = periods[0]
        found["elsewhere"] = [
            dict(date=iso(row["date"]), shift=row["shift"], schedule_id=period["id"])
            for period in periods[1:] for row in period.get("assignments") or []
            if row["employee"] == employee and iso(row["date"]) in dates
        ]
        own = sorted(
            (row for row in schedule.get("assignments") or []
             if row["employee"] == employee and iso(row["date"]) in dates),
            key=lambda row: (iso(row["date"]), _start(schedule, row)),
        )
        constraints = absence_constraints(employee, dates, reason or "היעדרות")
        fill = _Fill(profile, schedule, self._context.snapshot(team_id)["availability"],
                     constraints, [dict(action="remove", employee=employee, date=iso(row["date"]),
                                        shift=row["shift"], reason=reason or "היעדרות") for row in own])
        picks = {(row["date"], row["shift"]): row["employee"] for row in chosen or []}
        for row in own:
            date = iso(row["date"])
            result = self._tools.run(team_id, "find_replacements", {
                "schedule_id": schedule["id"], "employee": employee,
                "shift_name": row["shift"], "slot_date": date,
            })
            slot = fill.slot(row, schedule, result.get("candidates") or [],
                             picks.get((date, row["shift"]), ""))
            found["slots"].append(slot)
            # The chat's candidate cards show the same fair order as the plan.
            found["results"].append(dict(result, candidates=slot["candidates"]))
        busy = {slot["date"] for slot in found["slots"]} | {row["date"] for row in found["elsewhere"]}
        return dict(found, schedule_id=schedule["id"],
                    free_dates=[date for date in dates if date not in busy])

    def _periods_with_shifts(self, team_id, employee, dates) -> List[dict]:
        first, last = min(dates), max(dates)
        periods = []
        for row in self._repo.list_schedules(team_id):
            if iso(row["starts_on"]) > last or iso(row["ends_on"]) < first:
                continue
            period = self._repo.get_schedule(row["id"], team_id)
            if any(item["employee"] == employee and iso(item["date"]) in dates
                   for item in period.get("assignments") or []):
                periods.append(period)
        return sorted(periods, key=lambda period: iso(period["starts_on"]))


class _Fill:
    """The running hypothetical: removals first, then each pick as it lands."""

    def __init__(self, profile, schedule, availability, constraints, removals):
        self._profile, self._schedule = profile, schedule
        self._availability, self._constraints = availability, constraints
        self.operations = list(removals)
        self._known = self._warnings(self.operations)

    def slot(self, row: dict, schedule: dict, candidates: List[dict], chosen: str) -> dict:
        date, shift = iso(row["date"]), row["shift"]
        ranked = self._ranked(candidates)
        names = {person.get("name") for person in self._profile.get("employees") or []}
        pick, by = "", ""
        # The manager's own pick stands even if it warns: the plan card shows
        # the warning and approving it is their call (D3).
        if chosen in names and self._accept(chosen, shift, date, force=True):
            pick, by = chosen, "manager"
        else:
            pick = next((item["employee"] for item in ranked
                         if self._accept(item["employee"], shift, date)), "")
            by = "fairness" if pick else ""
        slot = _slot_times(schedule, shift, date)
        return dict(slot, date=date, shift=shift, replacing=row["employee"],
                    candidates=ranked, pick=pick, picked_by=by,
                    why="" if pick else _NO_PICK)

    def _ranked(self, candidates: List[dict]) -> List[dict]:
        load = self._load()
        ranked = [dict(item, **load.get(item["employee"], {})) for item in candidates]
        ranked.sort(key=lambda item: (
            item.get("hours", 0.0), item.get("shifts", 0), item.get("nights", 0),
            item["employee"],
        ))
        for item in ranked:
            item["why"] = "%s שעות · %d משמרות · %d לילות בתקופה" % (
                _pretty(item.get("hours", 0.0)), item.get("shifts", 0), item.get("nights", 0))
        return ranked

    def _accept(self, employee: str, shift: str, date: str, force: bool = False) -> bool:
        trial = self.operations + [dict(action="assign", employee=employee, date=date,
                                        shift=shift, reason="")]
        warnings = self._warnings(trial)
        if warnings is None or (not force and warnings - self._known):
            return False
        self.operations, self._known = trial, warnings
        return True

    def _warnings(self, operations) -> Optional[set]:
        try:
            rows = changed_rows(self._schedule, operations)
        except Exception:
            return None
        return {
            warning_key(row) for row in audit_plan(
                self._profile, self._schedule, rows, self._availability, self._constraints,
            )
            if row.get("code") not in GAP_CODES and row.get("severity", "warning") == "warning"
        }

    def _load(self) -> Dict[str, dict]:
        rows = changed_rows(self._schedule, self.operations)
        stats = shift_stats(rows, self._profile.get("shifts") or [],
                            self._profile.get("employees") or [],
                            slots=self._schedule.get("slots") or [], profile=self._profile)
        return {row["employee"]: dict(hours=row["hours"], shifts=row["shifts"],
                                      nights=row["nights"]) for row in stats["by_employee"]}


def _slot_times(schedule: dict, shift: str, date: str) -> dict:
    slot = next((row for row in schedule.get("slots") or []
                 if row.get("shift_name") == shift and iso(row.get("slot_date")) == date), {})
    return dict(start_time=str(slot.get("start_time") or "")[:5],
                end_time=str(slot.get("end_time") or "")[:5])


def _start(schedule: dict, row: dict) -> str:
    return _slot_times(schedule, row["shift"], iso(row["date"]))["start_time"]


def _pretty(hours: float) -> str:
    return "%g" % round(float(hours or 0), 1)
