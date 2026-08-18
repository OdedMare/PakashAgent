"""The management area: the period, the roster, constraints, and changes.

Routers delegate; the decisions live in `bl/`.

Two things this layer is responsible for stating clearly:

- **Every mutating route depends on `guards.boss()`.** That is where
  [D5](../../../docs/DECISIONS.md#d5--employees-are-read-only) is enforced —
  a member's cookie cannot reach a write no matter which URL it is aimed at.
  The single read route a member may use takes `visitor` and passes the role
  down, so it serves published periods only.
- **Propose and apply are two calls, and so are drag and confirm.** Neither
  is ever collapsed into one: the confirmation step is where the manager's
  reason is collected and where the agent's reasoning is read
  ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).

The team always comes from the signed session cookie. No route here accepts
a team id from the caller.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from app.api.contracts import (
    ApplyRequest,
    ConstraintRequest,
    GenerateRequest,
    ManagementOverview,
    MoveRequest,
    ProposeRequest,
    Proposal,
    Schedule,
)


def build_router(service, guards) -> APIRouter:
    router = APIRouter(prefix="/api/schedule", tags=["schedule"])
    boss = guards.boss()
    visitor = guards.visitor()

    @router.get("/overview", response_model=ManagementOverview)
    def overview(session: dict = Depends(visitor)) -> dict:
        """Everything the management area opens with.

        Served to members as well as the manager, and the role is passed
        down: a member gets published periods only, which is what makes
        their view a view of something finished rather than of the
        manager's working draft.
        """
        return service.overview(session["team_id"], session["role"])

    @router.get("/current")
    def current(session: dict = Depends(visitor)):
        """The period in play, or null when none has been built yet."""
        return service.current(session["team_id"], session["role"])

    @router.post("/generate", response_model=Schedule)
    def generate(
        request: GenerateRequest, session: dict = Depends(boss)
    ) -> dict:
        """Build a period. Stored as a draft — publishing is separate."""
        return service.generate(
            session["team_id"],
            starts_on=request.starts_on,
            ends_on=request.ends_on,
            instructions=request.instructions,
        )

    @router.post("/propose", response_model=Proposal)
    def propose(
        request: ProposeRequest, session: dict = Depends(boss)
    ) -> dict:
        """What the agent would do about a request. **Persists nothing.**

        Answers a request with no reason by asking for one
        (`needs_reason: true`) rather than by rejecting it: the manager made
        an omission, not an error.
        """
        return service.propose(
            session["team_id"],
            request.request,
            schedule_id=request.schedule_id,
            stated_reason=request.reason,
        )

    @router.post("/apply", response_model=Schedule)
    def apply(request: ApplyRequest, session: dict = Depends(boss)) -> dict:
        """Apply a proposal the manager confirmed, and log both reasons."""
        return service.apply(
            session["team_id"],
            request.schedule_id,
            [operation.model_dump() for operation in request.operations],
            reason=request.reason,
            agent_reason=request.agent_reason,
        )

    @router.post("/move", response_model=Schedule)
    def move(request: MoveRequest, session: dict = Depends(boss)) -> dict:
        """A drag the manager confirmed, with their reason attached.

        The drag itself changes nothing on the server — the calendar shows a
        confirmation first, and this is what that dialog sends. A dragged
        shift carries the same two reasons a spoken change does (D8).
        """
        return service.move(
            session["team_id"],
            request.assignment_id,
            request.shift_name,
            request.slot_date,
            reason=request.reason,
            agent_reason=request.agent_reason,
        )

    @router.get("/constraints/list")
    def constraints(
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        employee: Optional[str] = None,
        session: dict = Depends(visitor),
    ):
        """Recorded constraints. Readable by the team, writable by the manager."""
        return service.constraints(
            session["team_id"], starts_on, ends_on, employee
        )

    @router.post("/constraints")
    def set_constraint(
        request: ConstraintRequest, session: dict = Depends(boss)
    ):
        """Record a constraint. Boss-only: employees never write (D5)."""
        return service.set_constraint(
            session["team_id"],
            request.employee,
            request.constraint_date,
            shift_name=request.shift_name,
            available=request.available,
            reason=request.reason,
            source=request.source,
        )

    @router.delete("/constraints/{row_id}")
    def delete_constraint(
        row_id: str, session: dict = Depends(boss)
    ) -> dict:
        service.delete_constraint(row_id, session["team_id"])
        return {"status": "ok"}

    @router.get("/history/list")
    def history(
        schedule_id: Optional[str] = None,
        session: dict = Depends(visitor),
    ):
        """The append-only change log — the only history there is (D4)."""
        return service.history(session["team_id"], schedule_id)

    @router.post("/{schedule_id}/publish", response_model=Schedule)
    def publish(schedule_id: str, session: dict = Depends(boss)) -> dict:
        """Make a draft visible to the team."""
        return service.publish(schedule_id, session["team_id"])

    @router.post("/{schedule_id}/unpublish", response_model=Schedule)
    def unpublish(schedule_id: str, session: dict = Depends(boss)) -> dict:
        return service.unpublish(schedule_id, session["team_id"])

    @router.delete("/{schedule_id}")
    def delete(schedule_id: str, session: dict = Depends(boss)) -> dict:
        service.delete(schedule_id, session["team_id"])
        return {"status": "ok"}

    # Declared last on purpose: a path parameter at the root of the prefix
    # matches any single segment, so "/constraints" and "/history" would be
    # read as schedule ids if this came first. FastAPI resolves in
    # declaration order, which makes the ordering here load-bearing rather
    # than cosmetic.
    @router.get("/{schedule_id}", response_model=Schedule)
    def get(schedule_id: str, session: dict = Depends(boss)) -> dict:
        return service.get(schedule_id, session["team_id"])


    return router
