"""The workspace that owns the current model call."""

from contextlib import contextmanager
from contextvars import ContextVar


_team = ContextVar("pakash_llm_team", default="")


@contextmanager
def model_team(team_id: str):
    token = _team.set(team_id or "")
    try:
        yield
    finally:
        _team.reset(token)


def current_team() -> str:
    return _team.get()


__all__ = ["current_team", "model_team"]
