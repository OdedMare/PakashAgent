"""The agent speaking first (D15), and the period leaving as a file (D17)."""

from typing import Callable, List, Optional

from app.bl.audit import fairness
from app.bl.briefing.briefing import TRIGGER_OPENED
from app.bl.export.export import as_workbook, filename
from app.bl.schedule_service import rows
from app.bl.schedule_service.constants import RECENT_CHANGES
from app.bl.schedule_service.context import ScheduleContext


class BriefingService:
    """What the agent has to say, unprompted. Writes nothing; never raises.

    It gathers the state the management screen already shows and lets the
    agent say what it makes of it. Warnings and fairness are computed by
    `audit.py` and handed over as facts -- speaking first does not move the
    D3 line about which side does arithmetic. A failure costs the manager
    their briefing, never their calendar.
    """

    def __init__(
        self,
        context: ScheduleContext,
        briefing_agent,
        tools,
        current: Callable,
        observe_quietly: Callable,
    ):
        self._context = context
        self._repository = context.repository
        self._briefing = briefing_agent
        self._tools = tools
        self._current = current
        self._observe_quietly = observe_quietly

    def brief(
        self, team_id: str, trigger: str = TRIGGER_OPENED,
        last_said: Optional[List[str]] = None,
    ) -> dict:
        profile = self._context.profile(team_id)
        if not profile:
            # Before the interview the agent knows neither the shifts nor the
            # people; a briefing would be invented rather than observed.
            return rows.quiet_briefing()
        # Learning rides on the agent's own unprompted read, before the
        # briefing, so a pattern noticed now is in the table it describes.
        self._observe_quietly(team_id)
        schedule = self._current(team_id)
        readiness, gaps = self._publishing_state(team_id, schedule)
        try:
            return self._briefing.brief(
                trigger,
                profile,
                schedule=schedule,
                warnings=(schedule or {}).get("warnings") or [],
                fairness=fairness(
                    rows.assignment_facts((schedule or {}).get("assignments")),
                    rows.shifts(profile),
                    rows.employees(profile),
                ),
                requests=self._repository.list_requests(team_id, status="pending"),
                availability=self._context.availability(team_id, schedule),
                changes=self._repository.change_log(team_id, limit=RECENT_CHANGES),
                last_said=last_said,
                readiness=readiness,
                gaps=gaps,
            )
        except Exception:
            return rows.quiet_briefing()

    def _publishing_state(
        self, team_id: str, schedule: Optional[dict]
    ) -> tuple:
        """What publishing is waiting on, and which slots are short.

        Both from `bl/tools.py`, the same arithmetic the manager gets when
        they ask outright -- so the briefing and the answer to *"מה חסר לפני
        פרסום"* can never disagree. Empties rather than raising.
        """
        if not schedule:
            return {}, []
        try:
            readiness = self._tools.publish_readiness(
                team_id, schedule_id=rows.text(schedule.get("id"))
            )
            return readiness, readiness.get("gaps") or []
        except Exception:
            return {}, []


class WorkbookExporter:
    """One period as `.xlsx`, in the layout the importer reads back (D17).

    The unaudited stored schedule is passed deliberately: an export is a
    picture of what was decided, and warnings are advice about it, not part
    of the roster people read.
    """

    def __init__(self, context: ScheduleContext):
        self._context = context

    def workbook(
        self, team_id: str, schedule_id: Optional[str] = None
    ) -> tuple:
        schedule = self._context.require_schedule(team_id, schedule_id)
        title = rows.workplace_name(self._context.profile(team_id))
        return as_workbook(schedule, title=title), filename(schedule, "xlsx")
