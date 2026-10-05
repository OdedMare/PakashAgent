"""Reading the team and the period: overview, the period, one person's week."""

import datetime
from typing import List

from app.bl import rotation
from app.bl.audit import fairness
from app.bl.tools.reads import ToolReads, hours_for
from app.bl.tools.roster import find_person
from app.bl.tools.values import (
    audit_assignments, eligible, employees, iso, period_view, shifts, text,
    window,
)
from app.common.errors.errors import AgentError


class Tool:
    """One named, read-only question. Called as `tool(team_id, **arguments)`."""

    def __init__(self, reads: ToolReads):
        self._reads = reads


class TeamOverview(Tool):
    """The declared team and shift vocabulary, without schedule rows."""

    def __call__(self, team_id: str) -> dict:
        profile = self._reads.profile(team_id)
        if not profile:
            return {
                "found": False, "reason": "לא הוגדרו עדיין פרטי צוות",
                "employees": [], "shifts": [],
            }
        people = [
            {"name": text(row.get("name")), "role": text(row.get("role")),
             "eligible_shifts": eligible(row)}
            for row in employees(profile) if text(row.get("name"))
        ]
        declared = [
            {"name": text(row.get("name")),
             "start_time": text(row.get("start_time")),
             "end_time": text(row.get("end_time")),
             "is_on_call": bool(row.get("is_on_call"))}
            for row in shifts(profile) if text(row.get("name"))
        ]
        return {
            "found": True,
            "workplace": profile.get("workplace") or {},
            "employee_count": len(people),
            "employees": people,
            "shift_count": len(declared),
            "shifts": declared,
            "rules": profile.get("rules") or [],
        }


class ReadPeriod(Tool):
    """The schedule the manager means, with its warnings attached.

    `day` finds the stored period containing that date; `schedule_id` names
    one outright; neither means the current period. No period is an ordinary
    state, answered with `found: False` rather than raised.
    """

    def __call__(self, team_id: str, day: str = "", schedule_id: str = "") -> dict:
        schedule = self._reads.schedule(team_id, day=day, schedule_id=schedule_id)
        if schedule is None:
            return {
                "found": False, "reason": "אין סידור מאוחסן לתאריך הזה",
                "schedule": None,
            }
        profile = self._reads.profile(team_id)
        return {
            "found": True,
            "schedule": period_view(schedule),
            "assignments": audit_assignments(schedule),
            "slots": [dict(slot, slot_date=iso(slot.get("slot_date")))
                      for slot in schedule.get("slots") or []],
            # Pure rotation arithmetic, so the agent answers "who closes"
            # without deriving a cycle from names or dates.
            "closures": _closure_schedule(profile, schedule),
            "warnings": self._reads.warnings(team_id, schedule, profile),
            "fairness": fairness(
                audit_assignments(schedule), shifts(profile), employees(profile),
            ),
        }


class EmployeeState(Tool):
    """One person's week: their shifts, hours, constraints and warnings.

    An unknown name returns `found: False` with the roster attached, so the
    agent can ask *"התכוונת ל…"* against real names instead of inventing a
    person.
    """

    def __call__(
        self, team_id: str, employee: str, day: str = "", schedule_id: str = "",
    ) -> dict:
        name = text(employee)
        if not name:
            raise AgentError("צריך לציין שם עובד")
        profile = self._reads.profile(team_id)
        person = find_person(profile, name)
        if person is None:
            return {
                "found": False, "employee": name,
                "reason": "אין עובד/ת בשם הזה ברשימת הצוות",
                "roster": [text(row.get("name")) for row in employees(profile)],
            }
        schedule = self._reads.schedule(team_id, day=day, schedule_id=schedule_id)
        state = {
            "found": True,
            "employee": name,
            "role": text(person.get("role")),
            "eligible_shifts": eligible(person),
            "constraints": [
                row for row in self._reads.availability(team_id, window(schedule))
                if text(row.get("employee")) == name
            ],
        }
        if schedule is None:
            state.update({"shifts": [], "hours": 0.0, "warnings": [], "schedule": None})
            return state
        state.update(self._week(team_id, name, schedule, profile))
        return state

    def _week(self, team_id: str, name: str, schedule: dict, profile: dict) -> dict:
        worked = sorted(
            (
                {
                    "assignment_id": text(row.get("id")),
                    "shift": text(row.get("shift")),
                    "date": iso(row.get("date")),
                    "reason": text(row.get("reason")),
                }
                for row in schedule.get("assignments") or []
                if text(row.get("employee")) == name
            ),
            key=lambda row: (row["date"], row["shift"]),
        )
        return {
            "shifts": worked,
            "hours": hours_for(name, schedule, profile),
            "warnings": [
                row for row in self._reads.warnings(team_id, schedule, profile)
                if text(row.get("employee")) == name
            ],
            "schedule": period_view(schedule),
        }


def _closure_schedule(profile: dict, schedule: dict) -> List[dict]:
    try:
        start = datetime.date.fromisoformat(iso(schedule.get("starts_on")))
        end = datetime.date.fromisoformat(iso(schedule.get("ends_on")))
    except ValueError:
        return []
    return rotation.schedule_for_model(profile, start, end)
