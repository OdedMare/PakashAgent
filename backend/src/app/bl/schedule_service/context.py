"""The repository-backed reads every schedule collaborator shares.

One place answers "the audited view of this schedule", "the period in play",
and "the constraints over this window", so a write path and a read path can
never disagree about what a response carrying a schedule looks like.
"""

import datetime
from typing import List, Optional

from app.bl import rotation
from app.bl.audit import audit
from app.bl.scheduler import effective_availability
from app.bl.schedule_service import rows
from app.common.errors.errors import NotFoundError
from app.dal.repository.schedules import PREFERENCE_ACTIVE


class ScheduleContext:
    def __init__(self, repository):
        self._repository = repository

    @property
    def repository(self):
        return self._repository

    # -- plain reads ---------------------------------------------------------

    def profile(self, team_id: str) -> dict:
        return self._repository.team_profile(team_id) or {}

    def require_schedule(
        self, team_id: str, schedule_id: Optional[str]
    ) -> dict:
        if schedule_id:
            return self._repository.get_schedule(schedule_id, team_id)
        schedule = self._repository.current_schedule(team_id)
        if schedule is None:
            raise NotFoundError("אין סידור פעיל")
        return schedule

    def schedule_or_current(
        self, team_id: str, schedule_id: Optional[str]
    ) -> Optional[dict]:
        if schedule_id:
            return self._repository.get_schedule(schedule_id, team_id)
        return self._repository.current_schedule(team_id)

    def availability(self, team_id: str, schedule: Optional[dict]) -> List[dict]:
        """The stored constraints over the window a schedule covers."""
        start, end = rows.window(schedule)
        return self._repository.availability(team_id, start, end)

    def availability_facts(
        self, team_id: str, schedule: Optional[dict], with_reason: bool = True
    ) -> List[dict]:
        return [
            rows.availability_fact(row, with_reason)
            for row in self.availability(team_id, schedule)
        ]

    def active_preferences(self, team_id: str) -> List[dict]:
        """Confirmed standing context for every scheduling model call."""
        if not hasattr(self._repository, "preferences"):
            return []
        return self._repository.preferences(team_id, status=PREFERENCE_ACTIVE)

    # -- the audited view ----------------------------------------------------

    def view(self, schedule: dict, team_id: str) -> dict:
        """A schedule with its warnings attached.

        Warnings ride along on every response carrying a schedule, and a
        response with warnings is still a success — they are advisory
        ([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
        """
        schedule = dict(schedule)
        schedule["warnings"] = self.audit_rows(
            team_id, schedule.get("assignments") or [], schedule
        )
        schedule["closures"] = self.closures(team_id, schedule)
        return rows.dated(schedule)

    def fresh_view(self, schedule_id: str, team_id: str) -> dict:
        """Re-read a schedule after a write and return its audited view."""
        return self.view(
            self._repository.get_schedule(schedule_id, team_id), team_id
        )

    def result(self, schedule: dict, team_id: str, light: bool) -> dict:
        """The audited period, or just its progress counter when `light`."""
        if not light:
            return self.view(schedule, team_id)
        return progress_of(schedule)

    def audit_rows(
        self, team_id: str, assignments: List[dict], schedule: dict
    ) -> List[dict]:
        profile = self.profile(team_id)
        start, end = rows.window(schedule)
        return audit(
            rows.assignment_facts(assignments),
            rows.shifts(profile),
            rows.employees(profile),
            availability=effective_availability(
                profile,
                self._repository.availability(team_id, start, end),
                start, end,
            ),
            profile=profile,
            # The grid, so a slot with nobody on it is still checked. Without
            # it an entirely unstaffed shift leaves no row to notice and the
            # unfilled warning never fires -- the case most worth reporting.
            slots=[rows.audit_slot(slot) for slot in schedule.get("slots") or []],
        )

    def closures(self, team_id: str, schedule: dict) -> List[dict]:
        """Which of this period's dates belong to a closure, and to whom.

        Rides along with the schedule for the same reason the warnings do:
        the board has to render the week either way, and whose weekend a
        Thursday is cannot be worked out from the grid. It is read-only
        arithmetic from `bl/rotation.py` — there is no field here anything
        could act on, so a closure shown on a column stays a description of
        the cycle rather than a second way to change it.
        """
        start, end = rows.window(schedule)
        try:
            first = datetime.date.fromisoformat(rows.iso(start))
            last = datetime.date.fromisoformat(rows.iso(end))
        except (TypeError, ValueError):
            return []
        days = rotation.by_date(self.profile(team_id), first, last)
        return [days[date] for date in sorted(days)]


def progress_of(schedule: dict) -> dict:
    """Just the progress of a job, for the poll that watches it."""
    return {
        "id": schedule.get("id"),
        "status": schedule.get("status"),
        "generation": dict(schedule.get("generation") or {}),
    }
