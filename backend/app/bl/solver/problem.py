"""`Problem`: everything one solve needs, resolved before any variable exists.

The slot grid, the roster, the rows that are already fixed (pins, the rest
of the draft, recent history) and, for each person and slot, whether a
placement is legal at all. A placement that breaks a hard availability, a
rotation or closure window, eligibility or a hard `avoid` never becomes a
variable, so the model cannot even express it.
"""

import datetime
from typing import Dict, List, Optional

from app.bl import rotation
from app.bl.audit import constraint_conflicts, counts_toward_staffing
from app.bl.audit.roster import index_shifts, policy, row as timed_row, rows_of
from app.bl.solver.rows import assignment, eligible, employees, text, unique
from app.bl.rotation.presence import closure_status, presence_status
from app.bl.schedule_requests import covers, read_requests
from app.bl.scheduler.availability import effective_availability
from app.bl.scheduler.slots import build_slots
from app.common.errors import AgentError

# How far back history still matters: a run of days or a short rest does not
# start where the period does.
LOOKBACK_DAYS = 14


class Problem:
    def __init__(self, profile: dict, slots: List[dict], availability=None,
                 history=None, required_assignments=None, already_scheduled=None,
                 requests=None, keep=None):
        self.profile = profile or {}
        self.slots = slots
        self.shifts = index_shifts(self.profile.get("shifts") or [])
        self.employees = employees(self.profile)
        self.people = {text(person["name"]): person for person in self.employees}
        self.staff = [name for name, person in self.people.items()
                      if counts_toward_staffing(person, self.profile)]
        # נחפפים: placed beside a trainer, never in a seat (`rules._shadows`).
        self.shadows = [name for name in self.people if name not in self.staff]
        self.policy = policy(self.profile)
        self.requests = checked_requests(self.profile, requests)
        self.dates = sorted({slot["slot_date"] for slot in slots})
        first, last = (self.dates[0], self.dates[-1]) if self.dates else ("", "")
        self.availability = effective_availability(self.profile, availability, first, last) \
            if self.dates else []
        self.hard = [item for item in self.availability if item.get("is_hard", True) is not False]
        self.soft = [item for item in self.availability if item.get("is_hard", True) is False]
        self.keys = {(slot["shift_name"], slot["slot_date"]): index for index, slot in enumerate(slots)}
        self.times = [_slot_time(slot, self.shifts) for slot in slots]
        self.pins = self._pins(required_assignments)
        self.fixed = self._fixed(already_scheduled, history)
        self.legal = {(name, index): True for name in self.people
                      for index in range(len(slots)) if self._legal(name, index)}
        self.keep, self.kept_rows = self._keep(keep)

    # -- fixed rows ---------------------------------------------------------

    def _pins(self, required_assignments) -> List[dict]:
        pinned = []
        for raw in required_assignments or []:
            row = assignment(raw)
            if row is None or (row["shift"], row["date"]) not in self.keys:
                continue
            self._check_pin(row)
            row["reason"] = text(raw.get("reason")) or "שיבוץ חובה של המנהל"
            pinned.append(row)
        return unique(pinned)

    def _check_pin(self, row: dict) -> None:
        if row["employee"] not in self.people:
            raise AgentError("עובד/ת בשיבוץ החובה לא נמצא/ה בצוות")
        if not self._eligible(row["employee"], row["shift"]):
            raise AgentError("%s אינו/ה כשיר/ה למשמרת %s" % (row["employee"], row["shift"]))
        if self._blocked(row["employee"], self.keys[(row["shift"], row["date"])]):
            raise AgentError("שיבוץ החובה של %s ב-%s סותר אילוץ קשיח, נוכחות קבוצה, סבב או תלתון"
                             % (row["employee"], row["date"]))

    def _fixed(self, already_scheduled, history) -> List[dict]:
        """Rows that stand while the plan is solved: pins, the parts of the
        draft outside the plan, and recent history. Draft rows inside the
        plan are what is being rebuilt, so they are left out."""
        start = datetime.date.fromisoformat(self.dates[0]) if self.dates else None
        kept = [row for row in map(assignment, already_scheduled or []) if row
                and (row["shift"], row["date"]) not in self.keys]
        past = [row for row in map(assignment, history or []) if row and start
                and 0 < (start - datetime.date.fromisoformat(row["date"])).days <= LOOKBACK_DAYS]
        current = unique(self.pins + kept)
        rows = current + [row for row in unique(past) if _key(row) not in {_key(item) for item in current}]
        return [dict(row, past=row not in current, **_times(timed_row(row, self.shifts)))
                for row in rows]

    def _keep(self, keep) -> tuple:
        """The board's rows inside the plan, as {(name, slot): reason}, and
        how many there were. A row whose person, shift or legality is gone
        is counted (it is one the rebuild had to move) but cannot be kept."""
        pinned = {_key(row) for row in self.pins}
        rows = [row for row in unique([row for row in map(assignment, keep or []) if row])
                if (row["shift"], row["date"]) in self.keys and _key(row) not in pinned]
        kept = {}
        for row in rows:
            index = self.keys[(row["shift"], row["date"])]
            if (row["employee"], index) in self.legal:
                kept[(row["employee"], index)] = row["reason"]
        return kept, len(rows)

    def fixed_on(self, index: int) -> List[dict]:
        shift, date = self.slots[index]["shift_name"], self.slots[index]["slot_date"]
        return [row for row in self.fixed if row["shift"] == shift and row["date"] == date]

    # -- legality -----------------------------------------------------------

    def _eligible(self, name: str, shift: str) -> bool:
        return eligible(self.people[name], shift, self.shifts.get(shift),
                        list(self.shifts.values()), name in self.shadows)

    def _legal(self, name: str, index: int) -> bool:
        slot = self.slots[index]
        if not self._eligible(name, slot["shift_name"]):
            return False
        if any(row["employee"] == name for row in self.fixed_on(index)):
            return False
        if self._blocked(name, index):
            return False
        return not any(
            request["is_hard"] and request["kind"] == "avoid"
            and name in request["employees"]
            and covers(request, slot["shift_name"], slot["slot_date"])
            for request in self.requests
        )

    def _blocked(self, name: str, index: int) -> bool:
        """A hard availability, presence or closure forbids it."""
        slot = self.slots[index]
        candidate = self.candidate(name, index)
        if any(constraint_conflicts(candidate, item) for item in self.hard):
            return True
        profile = dict(self.profile, shifts=list(self.shifts.values()))
        person = self.people[name]
        status = presence_status(profile, person, slot)
        if status is None:
            status = closure_status(profile, person, slot)
        return status is False

    def candidate(self, name: str, index: int) -> dict:
        slot = self.slots[index]
        return {"employee": name, "shift": slot["shift_name"], "date": slot["slot_date"],
                "start_time": slot.get("start_time"), "end_time": slot.get("end_time")}

    def closes(self, name: str, index: int) -> bool:
        slot = self.slots[index]
        return rotation.holds(self.profile, self.people[name],
                              datetime.date.fromisoformat(slot["slot_date"]), slot["shift_name"])

    def candidates_of(self, name: str) -> List[int]:
        return [index for index in range(len(self.slots)) if (name, index) in self.legal]

    def holders(self, index: int, test) -> List[str]:
        return [name for name in self.staff if (name, index) in self.legal and test(self.people[name])]

    def trainers_of(self, name: str) -> List[str]:
        """Who may stand beside this נחפף/ת: their own `trainers`, else
        whoever can train, else (nobody can) any counted member."""
        listed = self.people[name].get("trainers")
        named = [text(item) for item in listed if text(item) in self.people] \
            if isinstance(listed, list) else []
        if named:
            return [item for item in named if item in self.staff]
        able = [item for item in self.staff if self.people[item].get("can_train")]
        return able or list(self.staff)


def checked_requests(profile: dict, requests: Optional[List[dict]]) -> List[dict]:
    """`requests` normalised, or an `AgentError` naming each one refused."""
    result, errors = read_requests(requests, profile)
    if errors:
        raise AgentError("לא ניתן לשבץ לפי הבקשות: %s." % "; ".join(errors))
    return result


def slots_for(profile: dict, starts_on: str, ends_on: str, shift_names=None) -> List[dict]:
    # Profile normalisation gives every roster a default exit pattern; only a
    # lettered group puts a person on an actual cycle that needs an anchor.
    grouped = [person for person in (profile or {}).get("employees") or []
               if isinstance(person, dict) and text(person.get("rotation_group"))]
    errors = rotation.configuration_errors(dict(profile or {}, employees=grouped))
    if errors:
        raise AgentError(
            "לא ניתן לשבץ לפני השלמת הגדרת הסבבים והתלתונים: %s." % "; ".join(errors))
    slots = build_slots(profile, starts_on, ends_on)
    wanted = {text(name) for name in shift_names or [] if text(name)}
    return [slot for slot in slots if not wanted or slot["shift_name"] in wanted]


def _key(row: dict) -> tuple:
    return row["employee"], row["shift"], row["date"]


def _slot_time(slot: dict, shifts: Dict[str, dict]) -> dict:
    probe = {"employee": "-", "shift": slot["shift_name"], "date": slot["slot_date"]}
    timed = rows_of([probe], shifts, [slot])
    return _times(timed[0]) if timed else _times(None)


def _times(timed) -> dict:
    """Start and end as datetimes (None when the shift has no clock), its
    weighted hours and whether it is a night."""
    if not timed:
        return {"begins": None, "ends": None, "hours": 0.0, "night": False}
    begins = ends = None
    if timed["day"] is not None and timed["start"] is not None and timed["end"] is not None:
        begins = datetime.datetime.combine(timed["day"], timed["start"].time())
        ends = datetime.datetime.combine(timed["day"], timed["end"].time())
        if timed["end"] <= timed["start"]:
            ends += datetime.timedelta(days=1)
    return {"begins": begins, "ends": ends, "hours": timed["hours"], "night": timed["is_night"]}
