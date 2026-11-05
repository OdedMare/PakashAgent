"""Who should cover an absent person's shifts, spread as evenly as possible.

Candidates arrive in stages (`placement/tiers.py`): the same role from the
seat's own post, then the same role from another post, then anyone else.
The fair pick is the lightest of the earliest stage that has a clean one.

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
from app.bl.chat.contract import GAP_CODES, audit_rows, changed_rows, plan_availability
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
              chosen: Optional[List[dict]] = None, reason: str = "",
              profile: Optional[dict] = None) -> dict:
        """The affected shifts, their ranked candidates and a fair pick each.

        `chosen` are the manager's own picks; they win over the fair one.
        One plan edits one stored period, so when the shifts sit in several
        the earliest is planned and the rest are listed in `elsewhere` --
        the absence itself is still saved for every date.
        """
        if profile is None:
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
        stored_availability = self._context.availability(team_id, schedule)
        fill = _Fill(profile, schedule, stored_availability,
                     constraints, [dict(action="remove", employee=employee, date=iso(row["date"]),
                                        shift=row["shift"], reason=reason or "היעדרות") for row in own])
        picks = {(row["date"], row["shift"]): row["employee"] for row in chosen or []}
        for row in own:
            date = iso(row["date"])
            result = self._tools.find_replacements.from_values(
                schedule, profile, stored_availability,
                employee=employee, shift_name=row["shift"], slot_date=date,
                # The changes tab must still offer a deliberate exception
                # when nobody fits cleanly; the candidate carries the exact
                # warning and the resulting plan still requires approval.
                include_exceptions=True,
                # Only the colleagues are shown; where the absent person could
                # go instead is no question an absence asks.
                include_other_slots=False,
            )
            result = dict(result, tool="find_replacements", ok=result.get("ok", True))
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
    """The running hypothetical: removals first, then each pick as it lands.

    A pick is checked the way `placement/context.py` checks a candidate:
    adding one row can only move the warnings about that person and about
    that slot, so only their rows are audited, before and after. Auditing
    the whole period per pick is what kept a long absence searching for
    minutes; the answer is the same.
    """

    def __init__(self, profile, schedule, availability, constraints, removals):
        self._profile, self._schedule = profile, schedule
        self._effective = plan_availability(profile, schedule, availability, constraints)
        self._grid: Dict[tuple, List[dict]] = {}
        for slot in schedule.get("slots") or []:
            key = (slot.get("shift_name"), iso(slot.get("slot_date")))
            self._grid.setdefault(key, []).append(slot)
        self.operations = list(removals)
        self._rows = self._apply(self.operations) or []

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
        # In stages first (`placement/tiers.py`): the same role from this
        # post, then from another, then anyone else. Inside a stage, fairness
        # is the number of shifts and nights, not hours (`solver/fairness.py`).
        ranked.sort(key=lambda item: (
            item.get("tier", 0), item.get("shifts", 0), item.get("nights", 0), item["employee"],
        ))
        for item in ranked:
            item["why"] = "%d משמרות · %d לילות בתקופה" % (
                item.get("shifts", 0), item.get("nights", 0))
        return ranked

    def _accept(self, employee: str, shift: str, date: str, force: bool = False) -> bool:
        trial = self.operations + [dict(action="assign", employee=employee, date=date,
                                        shift=shift, reason="")]
        rows = self._apply(trial)
        if rows is None:
            return False
        if not force and self._caused(employee, (shift, date), rows):
            return False
        self.operations, self._rows = trial, rows
        return True

    def _apply(self, operations) -> Optional[List[dict]]:
        try:
            return changed_rows(self._schedule, operations)
        except Exception:
            return None

    def _caused(self, employee: str, target: tuple, after: List[dict]) -> set:
        """Warnings the new row brings, read from its person and its slot."""
        before = self._warnings(self._scope(self._rows, employee, target), target)
        return self._warnings(self._scope(after, employee, target), target) - before

    @staticmethod
    def _scope(rows: List[dict], employee: str, target: tuple) -> List[dict]:
        return [row for row in rows
                if row["employee"] == employee or (row["shift"], iso(row["date"])) == target]

    def _warnings(self, rows: List[dict], target: tuple) -> set:
        pairs = {(row["shift"], iso(row["date"])) for row in rows} | {target}
        slots = self._schedule.get("slots") or []
        grid = [slot for pair in pairs for slot in self._grid.get(pair, [])]
        return {
            warning_key(row) for row in audit_rows(
                self._profile, rows, self._effective, grid or slots[:1],
            )
            if row.get("code") not in GAP_CODES and row.get("severity", "warning") == "warning"
        }

    def _load(self) -> Dict[str, dict]:
        stats = shift_stats(self._rows, self._profile.get("shifts") or [],
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


