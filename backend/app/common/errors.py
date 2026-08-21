"""Error types leaving the backend.

Messages are Hebrew: they reach a Hebrew-speaking boss directly, so the text
carried here is user-facing copy, not a developer string.
"""

from typing import List, Optional


class AppError(Exception):
    status_code = 400


class AgentError(AppError):
    """Anything the agent or the model layer failed to do.

    The error type everything in `dal/llm/` and `bl/` raises.
    """

    status_code = 502


class ProfileIncompleteError(AgentError):
    """The interview finished, but not with enough to build a grid.

    Its own type rather than a bare `AgentError` because the caller can *do*
    something about this one: the profile names exactly which required topics
    are still owed, so the failure carries them and the UI opens the
    interview on them instead of showing a dead end. Everything else in
    `bl/` failing is genuinely terminal for the request; this is a fork in
    the flow, and collapsing the two into one type is what made the manual
    path look broken rather than unfinished.

    `gaps` are the lines `bl/interview.py` produced -- the same definition
    the readiness gate uses, never a second copy. `blocks` says what each
    gap costs in the manager's terms.
    """

    def __init__(
        self,
        message: str,
        gaps: Optional[List[str]] = None,
        blocks: Optional[List[str]] = None,
    ) -> None:
        super().__init__(message)
        self.gaps = list(gaps or [])
        self.blocks = list(blocks or [])


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class AuthError(AppError):
    status_code = 401


class UnavailableError(AppError):
    """The process is alive but cannot accept work.

    503 rather than 500: nothing raised, and the service still answers — it
    has simply run out of the capacity to take on more.
    """

    status_code = 503


def error_payload(exc: AppError) -> dict:
    """The JSON body an `AppError` leaves as.

    Lives here rather than in the handler because it is not only the handler
    that builds it: the test harness mounts its own routers and its own
    handler, and when the two shaped the response separately a field added to
    one was invisible to the other -- which is precisely how a refusal can
    look, under test, like it carries nothing to act on.

    `detail` is always present and always the Hebrew sentence, so a client
    reading only that field is unaffected by anything added beside it.
    """
    payload = {"detail": str(exc)}
    if isinstance(exc, ProfileIncompleteError):
        # The one failure a caller can act on rather than only report.
        payload["gaps"] = exc.gaps
        payload["blocks"] = exc.blocks
        payload["can_resume_interview"] = True
    return payload
