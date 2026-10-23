"""The agent: propose/apply/move."""

from fastapi import APIRouter, Depends

from app.api.contracts import (
    ApplyRequest, MoveRequest, ProposeRequest, Proposal, Schedule,
)
from app.api.routers.schedules.base import RouteGroup


def _dumped(items) -> list:
    return [item.model_dump() for item in items]


class ChangeRoutes(RouteGroup):
    """Propose and apply are two calls, and so are drag and confirm (D8/D12)."""

    def register(self, router: APIRouter) -> None:
        self._register_suggesting(router)
        self._register_confirming(router)

    def _register_suggesting(self, router: APIRouter) -> None:
        """What the agent would say or do. Persists nothing."""
        service, boss = self.service, self.boss

        @router.post("/propose", response_model=Proposal)
        def propose(request: ProposeRequest, session: dict = Depends(boss)) -> dict:
            """What the agent would do about a request. **Persists nothing.**

            A request with no reason is answered by asking for one
            (`needs_reason`); one it cannot *target* by asking which
            (`needs_input`), with `pending_request` echoed for the answer.
            """
            return service.propose(
                session["team_id"],
                request.request,
                schedule_id=request.schedule_id,
                stated_reason=request.reason,
                pending_request=request.pending_request,
            )

    def _register_confirming(self, router: APIRouter) -> None:
        """What the manager confirmed, with their reason attached."""
        service, boss = self.service, self.boss

        @router.post("/apply")
        def apply(request: ApplyRequest, session: dict = Depends(boss)) -> dict:
            """Apply a proposal the manager confirmed, and log both reasons."""
            return service.apply(
                session["team_id"],
                request.schedule_id,
                _dumped(request.operations),
                reason=request.reason,
                agent_reason=request.agent_reason,
                profile_operations=_dumped(request.profile_operations),
            )

        @router.post("/move", response_model=Schedule)
        def move(request: MoveRequest, session: dict = Depends(boss)) -> dict:
            """A drag the manager confirmed, with their reason attached (D8)."""
            return service.move(
                session["team_id"],
                request.assignment_id,
                request.shift_name,
                request.slot_date,
                reason=request.reason,
                agent_reason=request.agent_reason,
                schedule_id=request.schedule_id,
            )
