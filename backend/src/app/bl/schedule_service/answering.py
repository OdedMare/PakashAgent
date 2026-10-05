"""Answering and imagining: read-only tools, and simulations (D19/D20)."""

from typing import List, Optional

from app.bl.simulate import simulate as simulate_operations
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.rows import text
from app.dal.repository.schedules import PREFERENCE_ACTIVE


class QuestionService:
    """Questions about the schedule, answered without a path to a write.

    The planner holds the tools, not the repository, and its response schema
    contains no operation -- there is nothing an `apply()` could read out of
    an answer. It works with no model configured: the planner falls back to
    `bl/intent.py` over the same tools.
    """

    def __init__(self, context: ScheduleContext, planner, tools):
        self._context = context
        self._repository = context.repository
        self._planner = planner
        self._tools = tools

    def ask(
        self,
        team_id: str,
        request: str,
        schedule_id: Optional[str] = None,
        pending_request: str = "",
    ) -> dict:
        schedule = self._context.schedule_or_current(team_id, schedule_id)
        answer = self._planner.answer(
            team_id,
            request,
            profile=self._context.profile(team_id),
            period=schedule,
            preferences=self._repository.preferences(
                team_id, status=PREFERENCE_ACTIVE
            ) if hasattr(self._repository, "preferences") else [],
            pending_request=pending_request,
        )
        answer["schedule_id"] = text((schedule or {}).get("id"))
        return answer

    def run_tool(
        self, team_id: str, name: str, arguments: Optional[dict] = None
    ) -> dict:
        """One named tool, run directly. Reads only.

        Routing the board's buttons through the same tool the agent uses is
        what keeps the button and the agent from giving different answers.
        """
        return self._tools.run(team_id, name, arguments)

    def simulate(
        self,
        team_id: str,
        operations: List[dict],
        schedule_id: Optional[str] = None,
    ) -> dict:
        """What a set of changes would do. **Persists nothing.**

        Deliberately not `propose()`: a manager thinking out loud has not
        asked for a confirm button. `bl/simulate.py` is handed no repository
        at all, and approving a simulation is an ordinary `apply()` with the
        manager's reason (D8/D12).
        """
        schedule = self._context.require_schedule(team_id, schedule_id)
        result = simulate_operations(
            schedule,
            self._context.profile(team_id),
            operations or [],
            availability=self._context.availability_facts(team_id, schedule),
        )
        result["schedule_id"] = schedule["id"]
        return result
