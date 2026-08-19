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

from typing import List, Optional

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response

from app.api.contracts import (
    ApplyRequest,
    AssignRequest,
    BlankRequest,
    Briefing,
    BriefingRequest,
    ConstraintRequest,
    GenerateRequest,
    ImportConfirmRequest,
    ImportPreview,
    ManagementOverview,
    MoveRequest,
    ProposeRequest,
    Proposal,
    Schedule,
    UnassignRequest,
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

    @router.post("/blank", response_model=Schedule)
    def blank(
        request: BlankRequest, session: dict = Depends(boss)
    ) -> dict:
        """Open an empty period the manager fills in themselves (D18).

        The authoring half of [D6](../../../docs/DECISIONS.md#d6--the-boss-can-author-or-generate).
        No model is called on this path at all — the grid is arithmetic over
        the declared shift vocabulary, and the cells arrive empty.
        """
        return service.create_blank(
            session["team_id"],
            starts_on=request.starts_on,
            ends_on=request.ends_on,
        )

    @router.post("/assign", response_model=Schedule)
    def assign(
        request: AssignRequest, session: dict = Depends(boss)
    ) -> dict:
        """Place one person on one slot, by hand. Writes immediately.

        Not a reversal of [D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit):
        a drag moves somebody who is already placed, which changes a person's
        week. Filling an empty cell takes nothing from anybody.
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
    def unassign(
        request: UnassignRequest, session: dict = Depends(boss)
    ) -> dict:
        """Take one person off a slot, by hand."""
        return service.unassign(
            session["team_id"],
            assignment_id=request.assignment_id,
            reason=request.reason,
            schedule_id=request.schedule_id,
        )

    @router.post("/brief", response_model=Briefing)
    def brief(
        request: BriefingRequest, session: dict = Depends(boss)
    ) -> dict:
        """What the agent has to say unprompted. **Persists nothing.**

        The one route here the manager did not initiate — the frontend calls
        it when the screen opens, after state changes, and before publishing
        ([D15](../../../docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).

        Boss-only, like every other agent route. A briefing reads drafts,
        pending requests and other people's stated reasons, none of which a
        member may see.

        It never fails: a briefing that could not be produced comes back
        quiet, because this sits beside a calendar that must render whatever
        the model is doing.
        """
        return service.brief(
            session["team_id"],
            trigger=request.trigger,
            last_said=request.last_said,
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

    @router.get("/export/{schedule_id}")
    def export(schedule_id: str, session: dict = Depends(boss)) -> Response:
        """One period as an `.xlsx` download.

        Boss-only. A member already reads the published roster through the
        share link; a file is a copy that leaves the app entirely, and
        handing that out is the manager's call
        ([D17](../../../docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).

        The filename is ASCII on purpose — a Hebrew one is correct but
        travels badly through `Content-Disposition`, and the period is what
        actually distinguishes one export from the next.
        """
        content, name = service.workbook(session["team_id"], schedule_id)
        return Response(
            content=content,
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": 'attachment; filename="%s"' % name},
        )

    @router.post("/import/preview", response_model=ImportPreview)
    async def import_preview(
        files: List[UploadFile] = File(...),
        learn_rules: bool = True,
        session: dict = Depends(boss),
    ) -> dict:
        """Read uploaded schedule files and return an interpretation.

        **This route writes nothing.** Under
        [D7](../../../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)
        the manager reads what the importer believes the files say and
        confirms it; `/import/confirm` is the only endpoint that persists.
        Splitting them across two calls is what makes the confirmation real
        rather than a dialog in front of a write that already happened.

        Takes many files at once because that is the actual case: the
        manager has a folder of past sheets, and patterns worth learning are
        only visible across them.

        Boss-only, like every schedule route
        ([D5](../../../docs/DECISIONS.md#d5--employees-are-read-only)/D14).
        """
        uploads = []
        for upload in files or []:
            uploads.append({
                "filename": upload.filename or "",
                "content": await upload.read(),
            })
        return service.preview_import(
            session["team_id"], uploads, learn_rules=learn_rules
        )

    @router.post("/import/confirm", response_model=Schedule)
    def import_confirm(
        request: ImportConfirmRequest, session: dict = Depends(boss)
    ) -> dict:
        """Store an interpretation the manager approved (D7).

        The rows come from the request rather than from a re-read of the
        file, so what is stored is exactly what was shown and approved —
        including any correction the manager made on the confirm screen.
        """
        return service.commit_import(
            session["team_id"],
            [row.model_dump() for row in request.assignments],
            [row.model_dump() for row in request.unavailability],
            starts_on=request.starts_on,
            ends_on=request.ends_on,
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

    @router.get("/history/learn")
    def learn_from_changes(session: dict = Depends(boss)) -> dict:
        """Candidate rules from what the manager kept correcting by hand.

        Boss-only and read-only. Nothing here is stored: these are proposals
        the manager approves one at a time (D7), exactly like the candidates
        an import produces — the endpoint that would *save* one is the
        interview, where rules live.

        Declared before `/{schedule_id}` for the reason the module docstring
        gives: a path parameter at the root of this prefix would otherwise
        read "history" as a schedule id.
        """
        return service.learn_from_changes(session["team_id"])

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
