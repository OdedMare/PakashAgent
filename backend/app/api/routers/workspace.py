"""Workspaces: create one, log into one, open a member's share link.

Routers delegate; the decisions live in `bl/`. What this layer owns is the
cookie -- issuing it on a successful login and clearing it on logout.
"""

from fastapi import APIRouter, Depends, Response

from app.api.contracts import (
    CreateTeamRequest,
    LoginRequest,
    PasswordChangeRequest,
    TeamSummary,
    TeamView,
    Workspace,
)
from app.common.sessions import COOKIE_NAME, ROLE_BOSS, ROLE_MEMBER, issue


def build_router(service, guards, secret: str, days: int) -> APIRouter:
    router = APIRouter(prefix="/api/workspace", tags=["workspace"])
    boss = guards.boss()
    visitor = guards.visitor()

    def _set_cookie(response: Response, team_id: str, role: str) -> None:
        """Sign the session into an HttpOnly cookie.

        `httponly` keeps it away from JavaScript, so an XSS bug cannot read
        it out. `samesite=lax` stops another site from silently issuing
        authenticated requests with it while still surviving the ordinary
        case of following a share link from a chat app.

        `secure` is deliberately NOT set: the app is served over plain HTTP
        in development and on the local network this product targets, and a
        `secure` cookie would simply never be stored there -- a login that
        appears to work and then does nothing. Set it at the reverse proxy
        when this is served over TLS.
        """
        response.set_cookie(
            COOKIE_NAME,
            issue(secret, team_id, role, days),
            max_age=days * 86400,
            httponly=True,
            samesite="lax",
            path="/",
        )

    @router.get("/teams", response_model=list)
    def teams() -> list:
        """Names for the login picker. Served unauthenticated by design --
        it is how a boss finds their workspace -- so it carries no secrets."""
        return service.list_teams()

    @router.post("", response_model=Workspace)
    def create(request: CreateTeamRequest, response: Response) -> dict:
        """Open a workspace and log its creator in as the boss."""
        team = service.create(request.name, request.password)
        _set_cookie(response, team["id"], ROLE_BOSS)
        return team

    @router.post("/login", response_model=Workspace)
    def login(request: LoginRequest, response: Response) -> dict:
        team = service.login(request.team_id, request.password)
        _set_cookie(response, team["id"], ROLE_BOSS)
        return team

    @router.post("/member/{token}", response_model=Workspace)
    def open_member_link(token: str, response: Response) -> dict:
        """Exchange a share link for a member session.

        The token moves into an HttpOnly cookie here so the rest of the
        member's visit does not carry it in the URL, where it would end up in
        history and in any screenshot of the address bar.
        """
        team = service.open_member_link(token)
        _set_cookie(response, team["id"], ROLE_MEMBER)
        return team

    @router.get("/me", response_model=TeamView)
    def me(session: dict = Depends(visitor)) -> dict:
        """The current workspace, shaped by the visitor's role."""
        return service.describe(session["team_id"], session["role"])

    @router.post("/logout")
    def logout(response: Response) -> dict:
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"status": "ok"}

    @router.post("/member-link/rotate", response_model=Workspace)
    def rotate(session: dict = Depends(boss)) -> dict:
        """Revoke the outstanding share link. Boss only."""
        return service.rotate_member_link(session["team_id"])

    @router.post("/password")
    def change_password(
        request: PasswordChangeRequest, session: dict = Depends(boss)
    ) -> dict:
        service.change_password(
            session["team_id"], request.current, request.replacement
        )
        return {"status": "ok"}

    return router
