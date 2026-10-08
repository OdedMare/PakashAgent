"""Route guards: who is asking, and may they.

FastAPI dependencies rather than middleware, so a route's signature states
its own access requirement -- `session: dict = Depends(deps.boss)` is visible
at the route, where a middleware rule matched on a path prefix is not, and a
new route added under the wrong prefix would silently inherit the wrong one.
"""

import secrets
import time
from threading import Lock

from fastapi import Cookie, Depends, Response
from typing import Callable, Dict, Optional, Tuple

from app.common.errors.errors import AuthError, ForbiddenError
from app.common.sessions.sessions import (
    ADMIN_COOKIE_NAME, COOKIE_NAME, ROLE_BOSS, ROLE_EMPLOYEE, issue, read,
    read_admin,
)

# How long a team's active/suspended answer is trusted before it is asked
# again. A suspension lands within this window on every worker; the operator
# console also clears this process's entry at once (`forget_team`).
_STATUS_TTL_SECONDS = 10.0

SUSPENDED_MESSAGE = "הצוות הושבת על ידי צוות משמרות זהב. פנו אלינו כדי להפעיל אותו מחדש"


class Guards:
    """Dependency factories bound to the process's signing secret.

    `team_active` answers whether a team still exists and is not suspended
    (D28). Without it -- the unit tests' default -- every signed cookie is
    taken at its word, which is how the guards behaved before the operator
    console existed.
    """

    def __init__(
        self, secret: str,
        team_active: Optional[Callable[[str], bool]] = None,
    ):
        self._secret = secret
        self._team_active = team_active
        self._status = {}  # type: Dict[str, Tuple[bool, float]]
        self._lock = Lock()

    def is_active(self, team_id: str) -> bool:
        """Cached `team_active`. A signed cookie outlives a suspension or a
        deletion by up to 30 days, so the cookie alone cannot answer this."""
        if self._team_active is None:
            return True
        now = time.monotonic()
        with self._lock:
            cached = self._status.get(team_id)
        if cached and now - cached[1] < _STATUS_TTL_SECONDS:
            return cached[0]
        active = bool(self._team_active(team_id))
        with self._lock:
            self._status[team_id] = (active, now)
        return active

    def forget_team(self, team_id: str) -> None:
        """Drop the cached answer, so a suspension applies on the next call."""
        with self._lock:
            self._status.pop(team_id, None)

    def require_active(self, team_id: str) -> None:
        """Refuse a sign-in to a suspended team before a cookie is issued.

        Called by the login routes only after the credential checked out, so
        the suspension is told to someone who proved they belong to the team
        rather than to anyone probing team ids.
        """
        if not self.is_active(team_id):
            raise ForbiddenError(SUSPENDED_MESSAGE)

    def admin_session(self, cookie: Optional[str]) -> Optional[dict]:
        """The operator payload behind a raw cookie value, or None."""
        return read_admin(self._secret, cookie)

    def admin(self):
        """The system operator -- the צוות משמרות זהב console (D28).

        Its own cookie, never a team role: an operator is above every
        workspace and belongs to none, so `boss()` refuses this session and
        this refuses every team session.
        """
        def dependency(
            pakash_admin: Optional[str] = Cookie(
                default=None, alias=ADMIN_COOKIE_NAME
            )
        ) -> dict:
            session = read_admin(self._secret, pakash_admin)
            if session is None:
                raise AuthError("נדרשת התחברות של צוות משמרות זהב")
            return session
        return dependency

    def visitor(self):
        """Any authenticated visitor -- boss, member, or employee."""
        def dependency(
            pakash_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)
        ) -> dict:
            return self.visitor_session(pakash_session)
        return dependency

    def visitor_session(self, cookie: Optional[str]) -> dict:
        """The team session behind a raw cookie value, or `AuthError`."""
        session = read(self._secret, cookie)
        if session is None:
            raise AuthError("נדרשת התחברות")
        # 401, not 403: the client answers it by returning to the login
        # screen, which is right for a team that was suspended or deleted
        # under an open session.
        if not self.is_active(session["team_id"]):
            raise AuthError(SUSPENDED_MESSAGE)
        return session

    def boss_session(self, cookie: Optional[str]) -> dict:
        """`visitor_session`, narrowed to the boss -- for a guard that must
        accept either a boss or the operator and so cannot `Depends(boss)`."""
        session = self.visitor_session(cookie)
        if session.get("role") != ROLE_BOSS:
            raise AuthError("הפעולה מותרת למנהל בלבד")
        return session

    def boss(self):
        """The boss of a workspace, and nobody else.

        Every route that touches a *schedule* depends on this. A member's
        cookie (from the share link) and an employee's cookie (from a claimed
        identity) are both refused here no matter which URL they are pointed
        at, which is what keeps "the manager remains the sole decider" a
        property of the routing layer rather than a convention
        ([D14](../../../docs/DECISIONS.md#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10)
        narrowed D5, it did not remove it).
        """
        def dependency(session: dict = Depends(self.visitor())) -> dict:
            if session.get("role") != ROLE_BOSS:
                raise AuthError("הפעולה מותרת למנהל בלבד")
            return session
        return dependency

    def employee(self):
        """A signed-in employee, acting as themselves.

        The narrow counterpart to `boss`. It admits exactly one kind of write
        -- a constraint *request* -- and nothing that touches a schedule; a
        route that assigns, moves, or publishes must depend on `boss` even if
        it feels employee-adjacent.

        The identity comes off the cookie, never off the request. That is the
        whole security property of the personal area: `session["employee"]` is
        signed, so an employee cannot read a colleague's hours or their stated
        reasons by putting another name in the body.
        """
        def dependency(session: dict = Depends(self.visitor())) -> dict:
            if session.get("role") != ROLE_EMPLOYEE:
                raise AuthError("נדרשת התחברות אישית")
            if not session.get("employee"):
                raise AuthError("נדרשת התחברות אישית")
            return session
        return dependency

    def manager(self):
        """Private chats under the existing shared-password manager login.

        A separate signed, HttpOnly identity survives logout in this browser.
        It is never accepted from a request body or shared with other browsers.
        """
        def dependency(
            response: Response,
            session: dict = Depends(self.boss()),
            pakash_manager: Optional[str] = Cookie(default=None),
        ) -> dict:
            owner = read(self._secret, pakash_manager)
            if not owner or owner.get("team_id") != session["team_id"] \
                    or not owner.get("manager_id"):
                owner = dict(session, manager_id=secrets.token_urlsafe(24))
                response.set_cookie(
                    "pakash_manager",
                    issue(self._secret, session["team_id"], ROLE_BOSS, 365,
                          manager_id=owner["manager_id"]),
                    httponly=True, samesite="lax", max_age=365 * 86400,
                    path="/",
                )
            return dict(session, manager_id=owner["manager_id"])
        return dependency


__all__ = ["Guards", "SUSPENDED_MESSAGE"]
