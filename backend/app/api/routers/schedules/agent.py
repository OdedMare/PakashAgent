"""The agent: briefing, propose/apply/move, asking, tools, simulating."""

from fastapi import APIRouter, Depends

from app.api.contracts import (
    AgentAnswer, ApplyRequest, AskRequest, Briefing, BriefingRequest,
    MoveRequest, ProposeRequest, Proposal, Schedule, SimulateRequest,
    Simulation, ToolRequest,
)
from app.api.routers.schedules.base import RouteGroup


def _dumped(items) -> list:
    return [item.model_dump() for item in items]


class ChangeRoutes(RouteGroup):
    """Propose and apply are two calls, and so are drag and confirm (D8/D12)."""

    def register(self, router: APIRouter) -> None:
        service, boss = self.service, self.boss

        @router.post("/brief", response_model=Briefing)
        def brief(request: BriefingRequest, session: dict = Depends(boss)) -> dict:
            """What the agent has to say unprompted. **Persists nothing.**

            Boss-only: a briefing reads drafts, pending requests and other
            people's stated reasons. It never fails -- a briefing that could
            not be produced comes back quiet (D15).
            """
            return service.brief(
                session["team_id"],
                trigger=request.trigger,
                last_said=request.last_said,
            )

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


class AskingRoutes(RouteGroup):
    """Asking and simulating write nothing, and carry no operations (D19/D20)."""

    def register(self, router: APIRouter) -> None:
        service, boss = self.service, self.boss

        @router.post("/ask", response_model=AgentAnswer)
        def ask(request: AskRequest, session: dict = Depends(boss)) -> dict:
            """Answer a question about the team or schedule. **Writes nothing.**

            There is no operation in the response, so nothing an answer says
            can be applied; a question that wants a change comes back with
            `needs_confirmation`. It answers with no model configured too.
            """
            return service.ask(
                session["team_id"],
                request=request.request,
                schedule_id=request.schedule_id,
                pending_request=request.pending_request,
            )

        @router.post("/tool")
        def tool(request: ToolRequest, session: dict = Depends(boss)) -> dict:
            """Run one named read-only tool directly. **Writes nothing.**

            An unknown tool comes back `ok: false` rather than as an error:
            the caller is a UI that has to render something.
            """
            return service.run_tool(session["team_id"], request.tool, request.arguments)

        @router.post("/simulate", response_model=Simulation)
        def simulate(request: SimulateRequest, session: dict = Depends(boss)) -> dict:
            """What a set of operations would do. **Persists nothing.**

            Approving a simulation is an ordinary `POST /apply` with the
            manager's reason: there is no shortcut from here to a change.
            """
            return service.simulate(
                session["team_id"],
                operations=_dumped(request.operations),
                schedule_id=request.schedule_id,
            )
