"""The צוות משמרות זהב operator console (D28).

Every route but `/login` depends on `guards.admin()`, visibly, at the route.
The operator's cookie is its own (`pakash_admin`), so signing in here never
touches a team session in the same browser, and a team's boss cookie is
refused on every route below.

What this layer owns beyond delegating: issuing and clearing the operator
cookie, and telling the guards to forget a team's cached status the moment
the operator suspends, resumes or deletes it -- so the change lands on the
next request in this process rather than after the cache window.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Response

from app.api.contracts import (
    AdminCreateTeamRequest,
    AdminDeleteRequest,
    AdminLoginRequest,
    AdminPasswordRequest,
    AdminReleaseRequest,
    AdminUpdateTeamRequest,
)
from app.common.sessions.sessions import ADMIN_COOKIE_NAME, issue_admin
from app.common.throttle.throttle import LoginThrottle

# One throttle key for the whole console: there is one operator password,
# so there is one account to guess at.
_THROTTLE_KEY = "admin"


class AdminRoutes:
    def __init__(self, service, guards, secret: str, hours: int, throttle):
        self._service = service
        self._guards = guards
        self._admin = guards.admin()
        self._secret = secret
        self._hours = hours
        self._throttle = throttle

    def register(self, router: APIRouter) -> None:
        self._register_session(router)
        self._register_reads(router)
        self._register_writes(router)

    def _register_session(self, router: APIRouter) -> None:
        service, throttle, admin = self._service, self._throttle, self._admin
        secret, hours = self._secret, self._hours

        @router.post("/login")
        def login(request: AdminLoginRequest, response: Response) -> dict:
            """Throttled like every other password check in the app."""
            throttle.attempt(_THROTTLE_KEY, lambda: service.login(request.password))
            # Same flags as the team cookie; see `routers/workspace.py` for
            # why `secure` is left to the reverse proxy.
            response.set_cookie(
                ADMIN_COOKIE_NAME, issue_admin(secret, hours),
                max_age=hours * 3600, httponly=True, samesite="lax", path="/",
            )
            return {"role": "admin"}

        @router.post("/logout")
        def logout(response: Response) -> dict:
            response.delete_cookie(ADMIN_COOKIE_NAME, path="/")
            return {"status": "ok"}

        @router.get("/me")
        def me(session: dict = Depends(admin)) -> dict:
            return {"role": "admin", "expires": session.get("exp")}

    def _register_reads(self, router: APIRouter) -> None:
        service, admin = self._service, self._admin

        @router.get("/overview")
        def overview(session: dict = Depends(admin)) -> dict:
            return service.overview()

        @router.get("/teams")
        def teams(session: dict = Depends(admin)) -> list:
            return service.teams()

        @router.get("/teams/{team_id}")
        def team(team_id: str, session: dict = Depends(admin)) -> dict:
            return service.team(team_id)

    def _register_writes(self, router: APIRouter) -> None:
        service, admin, guards = self._service, self._admin, self._guards

        @router.post("/teams")
        def create(
            request: AdminCreateTeamRequest, session: dict = Depends(admin)
        ) -> dict:
            return service.create(
                request.name, request.password,
                max_employees=request.max_employees, notes=request.notes,
            )

        @router.patch("/teams/{team_id}")
        def update(
            team_id: str, request: AdminUpdateTeamRequest,
            session: dict = Depends(admin),
        ) -> dict:
            # `exclude_unset`, so `max_employees: null` (remove the cap) and
            # an absent key (leave it) stay different requests.
            result = service.update(team_id, request.model_dump(exclude_unset=True))
            guards.forget_team(team_id)
            return result

        @router.post("/teams/{team_id}/password")
        def reset_password(
            team_id: str, request: AdminPasswordRequest,
            session: dict = Depends(admin),
        ) -> dict:
            service.reset_password(team_id, request.password)
            return {"status": "ok"}

        @router.post("/teams/{team_id}/member-link/rotate")
        def rotate(team_id: str, session: dict = Depends(admin)) -> dict:
            return service.rotate_link(team_id)

        @router.post("/teams/{team_id}/identities/release")
        def release(
            team_id: str, request: AdminReleaseRequest,
            session: dict = Depends(admin),
        ) -> dict:
            return service.release_identity(team_id, request.employee)

        @router.post("/teams/{team_id}/delete")
        def delete(
            team_id: str, request: AdminDeleteRequest,
            session: dict = Depends(admin),
        ) -> dict:
            """POST rather than DELETE: it carries a body (the name typed
            back), and a DELETE body is dropped by enough proxies to make the
            confirmation unreliable."""
            service.delete(team_id, request.confirm_name)
            guards.forget_team(team_id)
            return {"status": "deleted"}


def build_router(
    service, guards, secret: str, hours: int = 12,
    throttle: Optional[LoginThrottle] = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["admin"])
    AdminRoutes(
        service, guards, secret, hours, throttle or LoginThrottle()
    ).register(router)
    return router
