"""The intro interview, one turn at a time.

Routers delegate; the decisions live in `bl/`.
"""

from fastapi import APIRouter

from app.api.contracts import AnswerRequest, InterviewTurn


def build_router(service) -> APIRouter:
    router = APIRouter(prefix="/api/interview", tags=["interview"])

    @router.post("", response_model=InterviewTurn)
    def start() -> dict:
        """Open a new interview and return its first question."""
        return service.start()

    @router.get("/{session_id}", response_model=InterviewTurn)
    def resume(session_id: str) -> dict:
        """Re-serve the pending question. Costs no model call."""
        return service.resume(session_id)

    @router.post("/{session_id}/answer", response_model=InterviewTurn)
    def answer(session_id: str, request: AnswerRequest) -> dict:
        """Record an answer and return the next question, or the profile."""
        return service.answer(session_id, request.content)

    return router
