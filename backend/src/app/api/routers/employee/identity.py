"""Claiming a roster name, signing in as it, and signing out."""

from fastapi import APIRouter, Depends, Response

from app.api.contracts import (
    ClaimRequest,
    EmployeeLoginRequest,
    EmployeeSignInRequest,
)
from app.common.sessions.sessions import COOKIE_NAME, ROLE_EMPLOYEE, issue


class IdentityRoutes:
    def __init__(self, service, visitor, secret: str, days: int, throttle):
        self._service = service
        self._visitor = visitor
        self._secret = secret
        self._days = days
        self._throttle = throttle

    def sign_in(self, response: Response, team_id: str, name: str) -> None:
        """Upgrade the current session to a personal one.

        Same cookie and same flags as the workspace login -- see
        `routers/workspace.py` for why `secure` is left to the reverse proxy.
        The name is signed into the payload, which is what every personal
        read filters on.
        """
        response.set_cookie(
            COOKIE_NAME,
            issue(self._secret, team_id, ROLE_EMPLOYEE, self._days, employee=name),
            max_age=self._days * 86400,
            httponly=True,
            samesite="lax",
            path="/",
        )

    def register(self, router: APIRouter) -> None:
        service, visitor, sign_in = self._service, self._visitor, self.sign_in
        throttle = self._throttle

        @router.get("/roster")
        def roster(session: dict = Depends(visitor)) -> dict:
            """Names available to claim, and which are taken.

            Reachable with a plain share-link session -- the screen someone
            sees *before* they have an identity. Names and a claimed flag
            only, never a last-seen time.
            """
            return service.roster(session["team_id"])

        @router.post("/claim")
        def claim(
            request: ClaimRequest, response: Response,
            session: dict = Depends(visitor),
        ) -> dict:
            """Claim a roster name, then sign in as it immediately.

            The passcode was just chosen, and typing it again proves nothing.
            """
            result = service.claim(session["team_id"], request.employee, request.passcode)
            sign_in(response, session["team_id"], result["employee"])
            return result

        @router.post("/login")
        def login(
            request: EmployeeLoginRequest, response: Response,
            session: dict = Depends(visitor),
        ) -> dict:
            """Throttled per claimed name: a passcode is short enough that
            unlimited guesses would find it."""
            team_id = session["team_id"]
            key = "employee:%s:%s" % (team_id, request.employee.strip().lower())
            result = throttle.attempt(key, lambda: service.login(
                team_id, request.employee, request.passcode
            ))
            sign_in(response, session["team_id"], result["employee"])
            return result

        @router.post("/signin")
        def signin(request: EmployeeSignInRequest, response: Response) -> dict:
            """Sign in from the front door, with no share-link session (D25).

            Only reaches a name somebody already claimed -- the passcode is
            the credential, so the link adds nothing here. Claiming stays
            behind `visitor`, because without the link anyone who can see
            the team picker could take an unclaimed name. Shares `/login`'s
            throttle key, so the two doors do not double the guesses.
            """
            key = "employee:%s:%s" % (
                request.team_id, request.employee.strip().lower()
            )
            result = throttle.attempt(key, lambda: service.login(
                request.team_id, request.employee, request.passcode
            ))
            sign_in(response, request.team_id, result["employee"])
            return result

        @router.post("/logout")
        def logout(response: Response) -> dict:
            """Sign out of the personal identity.

            Clears the cookie entirely rather than downgrading to a member
            session: the share link is what grants that.
            """
            response.delete_cookie(COOKIE_NAME, path="/")
            return {"status": "ok"}
