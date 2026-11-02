"""What a מכלול commander does with duties, and what each team is told.

Every write names the מכלול from the commander's signed cookie; the team
and the duty type are checked against it (here, and again inside the SQL).
A write lands in the soldier's own team's change log under
`commander:<id>` (D4, D43), and reaches that team's commander as a notice.
"""

import datetime
from typing import Callable, Dict, List, Optional

from app.bl.audit import constraint_conflicts
from app.bl.complex_duties import values
from app.bl.complex_duties.collisions import DutyCollisions
from app.bl.complex_duties.planning import DutyPlanning
from app.bl.shared import text
from app.common.actor import acting_as
from app.common.errors import AgentError, ConflictError

ACTION_COMPLEX_DUTY = "complex_duty"
ACTION_COMPLEX_DUTY_CANCELLED = "complex_duty_cancelled"
ACTION_COMPLEX_DUTY_RECORDED = "complex_duty_recorded"

NOTICE_ASSIGNED = "שיבץ תורנות מכלול"
NOTICE_CANCELLED = "ביטל תורנות מכלול"
NOTICE_RECORDED = "רשם תורנות מכלול שכבר נעשתה"


class ComplexDutyService:
    def __init__(
        self, repository, complexes,
        notify: Optional[Callable[[str, str, str], None]] = None,
        schedules=None, today=None,
    ):
        """`complexes` is the `ComplexService` (which teams are this
        commander's); `notify(team_id, complex_id, action)` tells a team's
        commander, and must never fail the write that caused it."""
        self._repository = repository
        self._complexes = complexes
        self._notify = notify or (lambda *_: None)
        self._planning = DutyPlanning(repository, complexes, self)
        # `schedules` is the ScheduleService: what vacates a draft shift a new
        # duty collides with and refills it (`collisions.py`).
        self._collisions = DutyCollisions(schedules, self._notify, today)

    # --- the fair fill and the balance (`planning.py`) -------------------------

    def suggest(self, complex_id: str, start: str, end: str) -> dict:
        """The fairest soldier for every open seat in the span. Writes nothing."""
        return self._planning.suggest(complex_id, start, end)

    def approve(self, complex_id: str, rows: List[dict]) -> dict:
        """Seat what the commander kept of a suggestion, each like a hand-set duty."""
        return self._planning.approve(complex_id, rows)

    def balance(self, complex_id: str, start: str, end: str) -> dict:
        return self._planning.balance(complex_id, start, end)

    # --- duty types ----------------------------------------------------------

    def types(self, complex_id: str) -> List[dict]:
        return self._repository.complex_duty_types(complex_id)

    def create_type(self, complex_id: str, payload: Dict) -> dict:
        fields = values.type_fields(payload)
        fields.pop("active", None)
        return self._repository.create_complex_duty_type(complex_id, **fields)

    def update_type(self, complex_id: str, type_id: str, payload: Dict) -> dict:
        return self._repository.update_complex_duty_type(
            complex_id, type_id, values.type_fields(payload, partial=True),
        )

    def delete_type(self, complex_id: str, type_id: str) -> None:
        self._repository.delete_complex_duty_type(complex_id, type_id)

    # --- who stands which duty -----------------------------------------------

    def duties(self, complex_id: str, start: str, end: str) -> dict:
        first, last = values.span(start, end)
        return {
            "start": first.isoformat(), "end": last.isoformat(),
            "types": self.types(complex_id),
            "duties": self._repository.complex_duties(
                complex_id, first.isoformat(), last.isoformat(),
            ),
        }

    def assign(
        self, complex_id: str, type_id: str, team_id: str, employee: str,
        duty_date: str, note: str = "", blocks: bool = True, resolve: bool = True,
    ) -> dict:
        """Seat one soldier. Returns the duty and the stored shifts it now
        blocks: a warning for the commander, not a refusal (§4 of the plan);
        the team's commander is told either way.

        `blocks=False` records a duty already stood, or stood outside this
        system: it counts in fairness and statistics, blocks nothing, and
        is a fact rather than a plan -- so the type need not be running
        that weekday or still active, and no seat is checked."""
        day = values.parse_day(duty_date)
        employee = (employee or "").strip()
        team = self._complexes.require_team(complex_id, team_id)
        duty_type = self._repository.complex_duty_type(complex_id, type_id)
        self._check_soldier(team, employee, day)
        if blocks:
            self._check_type(complex_id, duty_type, day)
        duty = self._repository.set_complex_duty(
            complex_id, type_id, team["id"], employee, day.isoformat(),
            values.note(note), blocks=blocks,
        )
        if blocks:
            self._log(complex_id, duty, ACTION_COMPLEX_DUTY,
                      "שובץ/ה לתורנות %s על ידי מפקד המכלול" % duty_type["name"])
        else:
            self._log(complex_id, duty, ACTION_COMPLEX_DUTY_RECORDED,
                      "נרשמה תורנות %s שכבר נעשתה (נספרת בעומס, לא חוסמת)"
                      % duty_type["name"])
        self._notify(team["id"], complex_id, NOTICE_ASSIGNED if blocks else NOTICE_RECORDED)
        conflicts = self.conflicts(duty) if blocks else []
        if resolve and conflicts:
            conflicts = self.resolve(complex_id, conflicts)
        return {"duty": duty, "conflicts": conflicts}

    def resolve(self, complex_id: str, conflicts: List[dict]) -> List[dict]:
        """Vacate and refill the draft shifts the duties collide with; each
        conflict comes back with its `outcome` (`collisions.py`)."""
        return self._collisions.resolve(complex_id, conflicts)

    def cancel(self, complex_id: str, duty_id: str) -> dict:
        duty = self._repository.delete_complex_duty(complex_id, duty_id)
        self._log(complex_id, duty, ACTION_COMPLEX_DUTY_CANCELLED,
                  "תורנות %s בוטלה על ידי מפקד המכלול" % duty["duty_type"])
        self._notify(duty["team_id"], complex_id, NOTICE_CANCELLED)
        return duty

    def conflicts(self, duty: dict) -> List[dict]:
        """The soldier's stored shifts this duty blocks: that day's, and the
        night before that ends on its morning."""
        day = values.parse_day(duty["duty_date"])
        before = (day - datetime.timedelta(days=1)).isoformat()
        block = {
            "employee": duty["employee"], "date": day.isoformat(),
            "start_time": "", "end_time": "", "constraint_type": "duty",
        }
        rows = self._repository.soldier_shifts(
            duty["team_id"], duty["employee"], before, day.isoformat(),
        )
        return [
            {"assignment_id": row["id"], "team_id": duty["team_id"],
             "employee": duty["employee"], "duty_type": duty.get("duty_type", ""),
             "schedule_id": row["schedule_id"], "status": row["status"],
             "shift_name": row["shift_name"], "date": str(row["slot_date"])[:10],
             "start_time": row["start_time"], "end_time": row["end_time"]}
            for row in rows
            if constraint_conflicts(dict(
                employee=duty["employee"], date=str(row["slot_date"])[:10],
                shift=row["shift_name"], start_time=row["start_time"],
                end_time=row["end_time"],
            ), block)
        ]

    def roster(self, complex_id: str) -> List[dict]:
        """Every soldier of every משמרת in the מכלול, for the duty picker:
        name, role and the day they left, if they did."""
        teams = []
        for team in self._complexes.describe(complex_id)["teams"]:
            profile = self._repository.team_profile(team["id"]) or {}
            soldiers = [
                {"name": text(person.get("name")), "role": text(person.get("role")),
                 "inactive_from": text(person.get("inactive_from"))}
                for person in profile.get("employees") or []
                if isinstance(person, dict) and text(person.get("name"))
            ]
            teams.append({"id": team["id"], "name": team["name"],
                          "active": team["active"], "soldiers": soldiers})
        return teams

    # --- a team's own view ---------------------------------------------------

    def team_duties(self, team_id: str, start: str, end: str) -> List[dict]:
        first, last = values.span(start, end)
        return self._repository.team_complex_duties(
            team_id, first.isoformat(), last.isoformat(),
        )

    # --- checks --------------------------------------------------------------

    def _check_soldier(self, team: dict, employee: str, day: datetime.date) -> None:
        person = values.roster_person(
            self._repository.team_profile(team["id"]), employee,
        )
        if person is None:
            raise AgentError("%s לא נמצא/ת ברשימת החיילים של %s" % (
                employee or "החייל/ת", team["name"]))
        leaves = values.parse_day(person["inactive_from"]) \
            if person.get("inactive_from") else None
        if leaves is not None and leaves <= day:
            raise AgentError("%s סיים/ה את השירות במשמרת לפני התאריך הזה" % employee)

    def _check_type(self, complex_id: str, duty_type: dict, day: datetime.date) -> None:
        if not duty_type.get("active", True):
            raise AgentError("התורנות %s אינה פעילה" % duty_type["name"])
        if not values.runs_on(duty_type, day):
            raise AgentError("התורנות %s לא מתקיימת ביום הזה" % duty_type["name"])
        taken = sum(
            1 for row in self._repository.complex_duties(
                complex_id, day.isoformat(), day.isoformat(),
            )
            if row["duty_type_id"] == duty_type["id"]
        )
        if taken >= duty_type["seats"]:
            raise ConflictError("כל המקומות בתורנות %s ביום הזה כבר מאוישים"
                                % duty_type["name"])

    def _log(self, complex_id: str, duty: dict, action: str, words: str) -> None:
        """Into the soldier's own team's change log, as the commander --
        whichever cookie the request happened to carry beside theirs."""
        with acting_as("commander:" + complex_id):
            self._repository.append_change(
                duty["team_id"], action, employee=duty["employee"],
                slot_date=str(duty["duty_date"])[:10],
                reason=duty.get("note") or "", agent_reason=words,
            )
