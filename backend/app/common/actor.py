"""Who is acting, for the change log, without threading it through `bl/`.

Set once per request by the middleware in `main.py`, from the signed
cookies, and once per job by the worker, from what the request that queued
it recorded (`dal/repository/jobs.py`). `change_log.actor` is read from here,
so every write path records it without each call site passing it along.

An actor is `boss:<manager_id>` (or `boss` before that browser has one),
`employee:<name>`, `member` or `admin`; empty means the system itself -- a
job queued with no request behind it.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

_actor = ContextVar("pakash_actor", default="")


@contextmanager
def acting_as(actor: str):
    token = _actor.set(actor or "")
    try:
        yield
    finally:
        _actor.reset(token)


def current_actor() -> str:
    return _actor.get()


def actor_of(session: dict, manager: Optional[dict] = None) -> str:
    """The actor a signed session names. `manager` is the `pakash_manager`
    cookie, which tells one manager's browser from another's; it counts only
    for the team the session is for."""
    role = session.get("role") or ""
    if role == "boss":
        if manager and manager.get("team_id") == session.get("team_id") \
                and manager.get("manager_id"):
            return "boss:" + manager["manager_id"]
        return "boss"
    if role == "employee" and session.get("employee"):
        return "employee:" + session["employee"]
    return role
