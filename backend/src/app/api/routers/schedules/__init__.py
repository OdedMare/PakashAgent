"""The management area: the period, the roster, constraints, and changes.

Routers delegate; the decisions live in `bl/`. Two things this layer states
clearly:

- **Every mutating route depends on `guards.boss()`** (D5) — a member's cookie
  cannot reach a write no matter which URL it is aimed at. The reads a member
  may use take `visitor` and pass the role down.
- **Propose and apply are two calls, and so are drag and confirm** (D8).

The team always comes from the signed session cookie. No route here accepts a
team id from the caller.
"""

from fastapi import APIRouter

from app.api.routers.schedules.agent import AskingRoutes, ChangeRoutes
from app.api.routers.schedules.generation import GenerationRoutes
from app.api.routers.schedules.manual import ManualRoutes
from app.api.routers.schedules.periods import PeriodRoutes
from app.api.routers.schedules.reading import ReadingRoutes
from app.api.routers.schedules.records import ConstraintRoutes, PreferenceRoutes
from app.api.routers.schedules.transfer import TransferRoutes

# Order matters: every literal path is registered before `PeriodRoutes`,
# whose `/{schedule_id}` would otherwise swallow them.
_GROUPS = (
    ReadingRoutes,
    GenerationRoutes,
    ManualRoutes,
    ChangeRoutes,
    TransferRoutes,
    ConstraintRoutes,
    AskingRoutes,
    PreferenceRoutes,
    PeriodRoutes,
)


def build_router(service, guards) -> APIRouter:
    router = APIRouter(prefix="/api/schedule", tags=["schedule"])
    boss, visitor = guards.boss(), guards.visitor()
    for group in _GROUPS:
        group(service, boss, visitor).register(router)
    return router
