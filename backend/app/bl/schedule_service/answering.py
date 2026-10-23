"""Imagining: what a set of changes would do (D20)."""

from typing import List, Optional

from app.bl.simulate import simulate as simulate_operations
from app.bl.schedule_service.context import ScheduleContext


class Simulator:
    """What a set of changes would do, computed in memory. The manager
    chat's `simulate_changes` tool reads it; nothing here writes."""

    def __init__(self, context: ScheduleContext):
        self._context = context

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
