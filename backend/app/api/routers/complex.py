"""The commander of a מכלול (D43), and what the workplace manager is told.

The commander signs in on a cookie of their own (`pakash_commander`), sees
the combined board, and enters any one of their workplaces. Entering issues
an ordinary boss cookie for that team, marked with the מכלול; from there
every manager route serves the commander unchanged, and the guards re-check
on each request that the team is still theirs.

Every route states its guard at the route: `commander` for the מכלול's own
screens, `own_manager` for the notices only the workplace's manager reads.
"""

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Response

from app.api.contracts import CommanderLoginRequest
from app.api.routers.complex_duties import ComplexDutyRoutes
from app.common.sessions import (
    COMMANDER_COOKIE_NAME, COOKIE_NAME, ROLE_BOSS, issue, issue_commander,
    read,
)
from app.common.throttle import LoginThrottle


class ComplexRoutes:
    def __init__(self, service, guards, secret, days: int, throttle):
        self._service = service
        self._guards = guards
        self._secret = secret
        self._days = days
        self._throttle = throttle

    def _cookie(self, response: Response, name: str, value: str) -> None:
        # Same flags as the team cookie; see `routers/workspace.py`.
        response.set_cookie(
            name, value, max_age=self._days * 86400,
            httponly=True, samesite="lax", path="/",
        )

    def register(self, router: APIRouter) -> None:
        self._register_session(router)
        self._register_commander(router)
        self._register_notices(router)

    def _register_session(self, router: APIRouter) -> None:
        service, throttle, guards = self._service, self._throttle, self._guards
        secret, days, cookie = self._secret, self._days, self._cookie

        @router.get("/list")
        def complexes() -> list:
            """Names for the commander's login picker -- no secrets."""
            return service.list_public()

        @router.post("/login")
        def login(request: CommanderLoginRequest, response: Response) -> dict:
            found = throttle.attempt(
                "commander:%s" % request.complex_id,
                lambda: service.login(request.complex_id, request.password),
            )
            guards.forget_complexes()
            cookie(response, COMMANDER_COOKIE_NAME,
                   issue_commander(secret, found["id"], days))
            return found

        @router.post("/logout")
        def logout(
            response: Response,
            pakash_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
        ) -> dict:
            """Signs the commander out, and out of the workplace they were
            in. A manager's own team cookie in this browser is left alone."""
            response.delete_cookie(COMMANDER_COOKIE_NAME, path="/")
            team = read(secret, pakash_session)
            if team and team.get("commander"):
                response.delete_cookie(COOKIE_NAME, path="/")
            return {"status": "ok"}

    def _register_commander(self, router: APIRouter) -> None:
        service, secret, days = self._service, self._secret, self._days
        commander, cookie = self._guards.commander(), self._cookie

        @router.get("/me")
        def me(session: dict = Depends(commander)) -> dict:
            return service.describe(session["complex_id"])

        @router.get("/board")
        def board(
            start: str, end: str, session: dict = Depends(commander),
        ) -> dict:
            return service.board(session["complex_id"], start, end)

        @router.post("/teams/{team_id}/enter")
        def enter(
            team_id: str, response: Response,
            session: dict = Depends(commander),
        ) -> dict:
            """Open one workplace with a manager's powers. The team id comes
            from the path, and is accepted only if it is one of this
            commander's -- anything else is a 404."""
            team = service.require_team(session["complex_id"], team_id)
            cookie(response, COOKIE_NAME, issue(
                secret, team["id"], ROLE_BOSS, days,
                commander=session["complex_id"],
            ))
            return {"id": team["id"], "name": team["name"]}

        @router.post("/leave")
        def leave(
            response: Response,
            session: dict = Depends(commander),
            pakash_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
        ) -> dict:
            """Back to the combined board: drop the workplace cookie, if it
            is the commander's."""
            team = read(secret, pakash_session)
            if team and team.get("commander"):
                response.delete_cookie(COOKIE_NAME, path="/")
            return {"status": "ok"}

    def _register_notices(self, router: APIRouter) -> None:
        service, own_manager = self._service, self._guards.own_manager()

        @router.get("/notices")
        def notices(session: dict = Depends(own_manager)) -> dict:
            """What the commander changed in this workplace, unseen."""
            return service.notices(session["team_id"])

        @router.post("/notices/seen")
        def seen(session: dict = Depends(own_manager)) -> dict:
            service.mark_seen(session["team_id"])
            return {"status": "ok"}


def build_router(
    service, guards, secret, days: int,
    throttle: Optional[LoginThrottle] = None, duties=None,
) -> APIRouter:
    router = APIRouter(prefix="/api/complex", tags=["complex"])
    ComplexRoutes(
        service, guards, secret, days, throttle or LoginThrottle(),
    ).register(router)
    if duties is not None:
        ComplexDutyRoutes(duties, guards).register(router)
    return router
