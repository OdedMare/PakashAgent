"""Error types leaving the backend.

Messages are Hebrew: they reach a Hebrew-speaking boss directly, so the text
carried here is user-facing copy, not a developer string.
"""


class AppError(Exception):
    status_code = 400


class AgentError(AppError):
    """Anything the agent or the model layer failed to do.

    The error type everything in `dal/llm/` and `bl/` raises.
    """

    status_code = 502


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
