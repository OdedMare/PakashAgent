"""The repository reads every tool shares. Reads only -- never a write (D19)."""

from typing import List, Optional

from app.bl.audit import audit, fairness
from app.bl.tools.values import (
    audit_assignments, employees, iso, shifts, text, window,
)


class ToolReads:
    def __init__(self, repository):
        self._repository = repository

    def profile(self, team_id: str) -> dict:
        return self._repository.team_profile(team_id) or {}

    def schedule(
        self, team_id: str, day: str = "", schedule_id: str = ""
    ) -> Optional[dict]:
        """The period a tool call is about, by id, by date, or the current one.

        Every path goes through the repository with `team_id`, so a
        `schedule_id` the model produced out of thin air reads as missing
        rather than as another workspace's week (D10).
        """
        wanted = text(schedule_id)
        if wanted:
            try:
                return self._repository.get_schedule(wanted, team_id)
            except Exception:
                # Including NotFoundError: a period that is not this team's
                # is indistinguishable from one that does not exist.
                return None
        target = iso(day)
        if target:
            for period in self._repository.list_schedules(team_id):
                if iso(period["starts_on"]) <= target <= iso(period["ends_on"]):
                    return self._repository.get_schedule(period["id"], team_id)
            return None
        return self._repository.current_schedule(team_id)

    def availability(self, team_id: str, period: tuple) -> List[dict]:
        """Constraints over a period, in the shape `audit.py` reads."""
        return [
            {
                "employee": text(row.get("employee")),
                "date": iso(row.get("constraint_date")),
                "shift": text(row.get("shift_name")),
                "available": row.get("available"),
                "start_time": text(row.get("start_time")),
                "end_time": text(row.get("end_time")),
                "is_hard": row.get("is_hard", True),
                "reason": text(row.get("reason")),
                "source": text(row.get("source")),
            }
            for row in self._repository.availability(team_id, period[0], period[1])
        ]

    def warnings(self, team_id: str, schedule: dict, profile: dict) -> List[dict]:
        """The audit over a stored period. The same call the overview makes."""
        return audit(
            audit_assignments(schedule),
            shifts(profile),
            employees(profile),
            self.availability(team_id, window(schedule)),
            profile,
            [
                dict(slot, slot_date=iso(slot.get("slot_date")))
                for slot in schedule.get("slots") or []
            ],
        )

    def pending_requests(self, team_id: str) -> List[dict]:
        """Employee constraint submissions awaiting a ruling (D14).

        Read through `getattr` because not every repository handed to the
        tools owns the identities table; a check that crashed without one
        would make the tool unusable for a workspace that never turned them on.
        """
        reader = getattr(self._repository, "pending_constraint_requests", None)
        if reader is None:
            return []
        try:
            return list(reader(team_id) or [])
        except Exception:
            return []


def hours_for(employee: str, schedule: dict, profile: dict) -> float:
    """One person's assigned hours in this period, weighted as the audit does."""
    totals = fairness(audit_assignments(schedule), shifts(profile), employees(profile))
    for row in totals.get("people") or []:
        if text(row.get("employee")) == employee:
            return float(row.get("hours") or 0.0)
    return 0.0
