"""The employee's own area: claim an identity, read your hours, ask for a day.

The HTTP half of D14. **Every route is scoped by a name taken off the signed
cookie**, never from the body or the path — a signed-in employee cannot read a
colleague's hours because there is nowhere to put another name.

**Nothing here mutates a schedule.** The one write an employee gets is a
constraint *request*, which lands pending and is invisible to `bl/audit.py`
until a manager approves it. Routes that decide depend on `guards.boss()`.

Route order matters: literal paths are declared before `/{request_id}`.
"""

from typing import Optional

from fastapi import APIRouter

from app.api.routers.employee.identity import IdentityRoutes
from app.api.routers.employee.live import LiveRoutes
from app.api.routers.employee.manager import RequestDecisionRoutes, SwapDecisionRoutes
from app.api.routers.employee.personal import EmployeeSwapRoutes, PersonalRoutes
from app.common.events import TeamEvents
from app.common.throttle.throttle import LoginThrottle


def build_router(
    service, guards, secret: str, days: int,
    throttle: Optional[LoginThrottle] = None,
    events: Optional[TeamEvents] = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/employee", tags=["employee"])
    employee = guards.employee()
    IdentityRoutes(
        service, guards.visitor(), secret, days, throttle or LoginThrottle(),
        guards.require_active,
    ).register(router)
    PersonalRoutes(service, employee, events).register(router)
    EmployeeSwapRoutes(service, employee, events).register(router)
    return router


def build_manager_router(
    service, guards, events: Optional[TeamEvents] = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/schedule/requests", tags=["requests"])
    if events is not None:
        LiveRoutes(events, guards.boss()).register(router)
    RequestDecisionRoutes(service, guards.boss()).register(router)
    return router


def build_swap_router(service, guards) -> APIRouter:
    router = APIRouter(prefix="/api/schedule/swaps", tags=["swaps"])
    SwapDecisionRoutes(service, guards.boss()).register(router)
    return router
