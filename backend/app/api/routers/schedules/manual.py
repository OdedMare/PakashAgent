"""The manual path (D18): placing by hand, and checking before the click."""

from fastapi import APIRouter, Depends

from app.api.contracts import (
    AssignRequest, CheckRequest, PlacementCheck, Schedule, UnassignRequest,
)
from app.api.routers.schedules.base import RouteGroup


class ManualRoutes(RouteGroup):
    def register(self, router: APIRouter) -> None:
        service, boss = self.service, self.boss

        @router.post("/assign", response_model=Schedule)
        def assign(request: AssignRequest, session: dict = Depends(boss)) -> dict:
            """Place one person on one slot, by hand. Writes immediately.

            Not a reversal of D12: a drag moves somebody who is already
            placed, while filling an empty cell takes nothing from anybody.
            """
            return service.assign(
                session["team_id"],
                shift_name=request.shift_name,
                slot_date=request.slot_date,
                employee=request.employee,
                reason=request.reason,
                schedule_id=request.schedule_id,
            )

        @router.post("/unassign", response_model=Schedule)
        def unassign(request: UnassignRequest, session: dict = Depends(boss)) -> dict:
            """Take one person off a slot, by hand."""
            return service.unassign(
                session["team_id"],
                assignment_id=request.assignment_id,
                reason=request.reason,
                schedule_id=request.schedule_id,
            )

        @router.post("/check", response_model=PlacementCheck)
        def check(request: CheckRequest, session: dict = Depends(boss)) -> dict:
            """What a placement would cost, before it is made. **Writes nothing.**

            **No model is called on this path** — it is `bl/placement.py`,
            which is what lets the board validate a drag with the agent
            unavailable (D3). Advice, not a gate: `blocking` is always false.
            """
            return service.check_placement(
                session["team_id"],
                employee=request.employee,
                shift_name=request.shift_name,
                slot_date=request.slot_date,
                schedule_id=request.schedule_id,
                moving_assignment_id=request.moving_assignment_id,
            )
