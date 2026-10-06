"""Reading the schedule: the period in play, the board's overview, a check."""

from typing import List, Optional

from app.bl.audit import shift_stats
from app.bl.placement import check as check_placement
from app.bl.schedule_service import rows
from app.bl.schedule_service.constants import RECENT_CHANGES
from app.bl.schedule_service.context import ScheduleContext
from app.common.errors.errors import AgentError
from app.common.time_context.time_context import israel_today


class ScheduleReader:
    def __init__(self, context: ScheduleContext):
        self._context = context
        self._repository = context.repository

    def current(self, team_id: str, role: str = "boss") -> Optional[dict]:
        """The period in play, audited, or None when there is none yet.

        A member sees only published schedules. A draft is the manager's
        working state, and publishing is the act that makes it the team's
        ([D5](../../../../docs/DECISIONS.md#d5--employees-are-read-only)).
        """
        schedule = self._repository.current_schedule(
            team_id, published_only=(role != "boss")
        )
        if schedule is None:
            return None
        return self._context.view(schedule, team_id)

    def get(self, schedule_id: str, team_id: str) -> dict:
        return self._context.fresh_view(schedule_id, team_id)

    def list_periods(self, team_id: str) -> List[dict]:
        return self._repository.list_schedules(team_id)

    def period_at(
        self, team_id: str, day: str, role: str = "boss"
    ) -> Optional[dict]:
        """The stored period containing `day`, or None when none does.

        What the board opens on. "Which stored period covers today" is a
        comparison of two dates -- arithmetic, so it is answered here rather
        than by asking the client to guess from `list_periods`.

        A member gets published periods only, exactly as `current()` does:
        a draft is still the manager's working state until they publish (D5).
        """
        wanted = rows.iso(day)
        if not wanted:
            raise AgentError("התאריך אינו תקין")
        for period in self._repository.list_schedules(team_id):
            if role != "boss" and period.get("status") != "published":
                continue
            if rows.iso(period["starts_on"]) <= wanted <= rows.iso(period["ends_on"]):
                return self._context.fresh_view(period["id"], team_id)
        return None

    def check_placement(
        self,
        team_id: str,
        employee: str,
        shift_name: str,
        slot_date: str,
        schedule_id: Optional[str] = None,
        moving_assignment_id: str = "",
    ) -> dict:
        """What a placement would cost, before it is made. Writes nothing.

        **No model call.** This is `bl/placement.py` handed the stored
        schedule, and it is what makes the board work with the agent
        unavailable. It does not gate the write that follows: the audit
        advises and never blocks
        ([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
        """
        schedule = self._context.require_schedule(team_id, schedule_id)
        return check_placement(
            schedule,
            self._context.profile(team_id),
            employee=employee,
            shift_name=shift_name,
            slot_date=slot_date,
            availability=self._context.availability_facts(team_id, schedule),
            moving_assignment_id=moving_assignment_id,
        )

    def overview(self, team_id: str, role: str = "boss") -> dict:
        """Everything the management area opens with, in one call.

        One request rather than six because they are read together and a
        half-loaded management screen is worse than a slightly slower one.
        Dates out of SQL are normalised to strings on the way out, since these
        lists are read straight from the repository rather than through
        `view`.
        """
        profile = self._context.profile(team_id)
        schedule = self.current(team_id, role)
        return {
            "today": israel_today().isoformat(),
            "profile": profile,
            "employees": rows.employees(profile),
            "shifts": rows.shifts(profile),
            "schedule": schedule,
            "periods": [
                rows.period_row(row)
                for row in self._repository.list_schedules(team_id)
            ],
            "availability": [
                dict(row, constraint_date=rows.iso(row.get("constraint_date")))
                for row in self._context.availability(team_id, schedule)
            ],
            "changes": [
                rows.change_row(row)
                for row in self._repository.change_log(
                    team_id, limit=RECENT_CHANGES
                )
            ],
            # A report, never a grade -- nothing here gates publishing (D3).
            "stats": self._stats(team_id, profile, schedule),
        }

    def _stats(
        self, team_id: str, profile: dict, schedule: Optional[dict]
    ) -> dict:
        """The current period's numbers, or empty totals when there is none.

        Computed by `audit.py` rather than in the browser: a chart drawn from
        a second implementation of the hours arithmetic would eventually
        disagree with the warning printed beside it. Slots carry `headcount`
        so coverage is measured against what this grid actually asks for, and
        the profile carries the shadow-shift flags.
        """
        if not schedule:
            return shift_stats([], rows.shifts(profile), rows.employees(profile))
        return shift_stats(
            rows.assignment_facts(schedule.get("assignments")),
            rows.shifts(profile),
            rows.employees(profile),
            slots=[rows.stats_slot(slot) for slot in schedule.get("slots") or []],
            warnings=schedule.get("warnings") or [],
            profile=profile,
            availability=self._context.availability_facts(
                team_id, schedule, with_reason=False
            ),
        )
