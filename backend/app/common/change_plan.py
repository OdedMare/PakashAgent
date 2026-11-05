"""The change plan currently being applied.

Like ``actor.py``, this is request-local context rather than an argument every
repository write has to carry.  Change-log rows created by one approved plan
can therefore be correlated without coupling the domain services to plans.
"""

from contextlib import contextmanager
from contextvars import ContextVar


_plan_id = ContextVar("pakash_change_plan", default="")


@contextmanager
def applying_plan(plan_id: str):
    token = _plan_id.set(plan_id or "")
    try:
        yield
    finally:
        _plan_id.reset(token)


def current_plan_id() -> str:
    return _plan_id.get()
