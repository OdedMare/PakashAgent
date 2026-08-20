"""The intro interview, one turn at a time.

Routers delegate; the decisions live in `bl/`.

Every route here is boss-only. The interview is how the workplace gets taught,
which is authoring — D5 keeps employees on the reading side of the product, so
a member's session cannot reach any of it.
"""

from fastapi import APIRouter, Depends

from app.api.contracts import AnswerRequest, InterviewTurn


def build_router(service, guards) -> APIRouter:
    router = APIRouter(prefix="/api/interview", tags=["interview"])
    boss = guards.boss()

    @router.post("", response_model=InterviewTurn)
    def start(session: dict = Depends(boss)) -> dict:
        """Open a new interview and return its first question."""
        return service.start(session["team_id"])

    @router.post("/continue", response_model=InterviewTurn)
    def extend(session: dict = Depends(boss)) -> dict:
        """Reopen the finished interview to add to it.

        The same conversation continues, so the boss answers only what is
        new. Declared above `/{session_id}` even though the methods differ,
        following the rule that keeps `schedules.py` readable: a literal path
        sitting under a path parameter is one method away from unreachable.
        """
        return service.extend(session["team_id"])

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
        return service.answer(session_id, session["team_id"], request.content)

    @router.post("/{session_id}/finish", response_model=InterviewTurn)
    def finish(session_id: str, session: dict = Depends(boss)) -> dict:
        """End the interview on what has been gathered so far.

        Returns the completed profile, or — when the draft still cannot
        produce a schedule — the next question about exactly what is missing,
        with those gaps named in `gaps`. Whether finishing is allowed is
        decided in `bl/`, from the draft, never by the caller asserting it.
        """
        return service.finish(session_id, session["team_id"])

    return router
