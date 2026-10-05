"""The intro interview, one turn at a time.

Routers delegate; the decisions live in `bl/`.

Every route here is boss-only. The interview is how the workplace gets taught,
which is authoring — D5 keeps employees on the reading side of the product, so
a member's session cannot reach any of it.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from app.api.contracts import AnswerRequest, InterviewSeed, InterviewTurn


def build_router(service, guards) -> APIRouter:
    router = APIRouter(prefix="/api/interview", tags=["interview"])
    boss = guards.boss()

    @router.post("", response_model=InterviewTurn)
    def start(
        request: Optional[InterviewSeed] = None,
        session: dict = Depends(boss),
    ) -> dict:
        """Open a new interview and return its first question."""
        return service.start(
            session["team_id"], request.model_dump() if request else None
        )

    @router.get("/{session_id}", response_model=InterviewTurn)
    def resume(session_id: str, session: dict = Depends(boss)) -> dict:
        """Re-serve the pending question. Costs no model call."""
        return service.resume(session_id, session["team_id"])

    @router.post("/{session_id}/answer", response_model=InterviewTurn)
    def answer(
        session_id: str,
        request: AnswerRequest,
        session: dict = Depends(boss),
    ) -> dict:
        """Record an answer and return the next question, or the profile."""
        return service.answer(
            session_id, session["team_id"], request.content, request.mode
        )

    @router.post("/{session_id}/retry", response_model=InterviewTurn)
    def retry(session_id: str, session: dict = Depends(boss)) -> dict:
        """Retry the current background generation without duplicating input."""
        return service.retry(session_id, session["team_id"])

    @router.post("/{session_id}/end", response_model=InterviewTurn)
    def end(session_id: str, session: dict = Depends(boss)) -> dict:
        """Close the interview now and keep what was collected.

        The manager's escape hatch from an interview that is longer than the
        afternoon they have for it. Costs no model call, so it works when the
        model is what made them want to leave.
        """
        return service.end(session_id, session["team_id"])

    return router
