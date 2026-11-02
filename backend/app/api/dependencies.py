"""Route authentication and authorization guards.

FastAPI dependencies rather than middleware, so a route's signature states
its own access requirement -- `session: dict = Depends(deps.boss)` is visible
at the route, where a middleware rule matched on a path prefix is not, and a
new route added under the wrong prefix would silently inherit the wrong one.
"""

import secrets
import time
from threading import Lock

from fastapi import Cookie, Depends, Response
from typing import Callable, Optional

from app.common.errors import AuthError, ForbiddenError
from app.common.sessions import (
    ADMIN_COOKIE_NAME, COMMANDER_COOKIE_NAME, COOKIE_NAME,
    MANAGER_COOKIE_NAME, ROLE_BOSS, ROLE_EMPLOYEE, issue, read, read_admin,
    read_commander,
)

# How long a team's active/suspended answer is trusted before it is asked
# again. A suspension lands within this window on every worker; the operator
# console also clears this process's entry at once (`forget_team`).
_STATUS_TTL_SECONDS = 10.0

SUSPENDED_MESSAGE = "הצוות הושבת על ידי צוות משמרות זהב. פנו אלינו כדי להפעיל אותו מחדש"
UNLINKED_MESSAGE = "המשמרת אינה משויכת עוד למכלול שלך"


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
        team_in_complex: Optional[Callable[[str, str], bool]] = None,
        complex_active: Optional[Callable[[str], bool]] = None,
    ):
        self._secret = secret
        self._team_active = team_active
        # D43: is this team still linked to this מכלול (and both on)? And is
        # this מכלול still on? Without them -- tests -- a commander cookie is
        # taken at its word, as `team_active` is.
        self._team_in_complex = team_in_complex
        self._complex_active = complex_active
        self._status: dict[str, tuple[bool, float]] = {}
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

    def forget_complexes(self) -> None:
        """Drop every cached מכלול answer -- after the operator links,
        unlinks, suspends or deletes one."""
        with self._lock:
            for key in [key for key in self._status if key.startswith("c:")]:
                self._status.pop(key, None)

    def _cached(self, key: str, ask: Callable[[], bool]) -> bool:
        now = time.monotonic()
        with self._lock:
            cached = self._status.get(key)
        if cached and now - cached[1] < _STATUS_TTL_SECONDS:
            return cached[0]
        answer = bool(ask())
        with self._lock:
            self._status[key] = (answer, now)
        return answer

    def commander_reaches(self, team_id: str, complex_id: str) -> bool:
        """True while `team_id` is one of this commander's workplaces."""
        if self._team_in_complex is None:
            return True
        return self._cached(
            "c:%s:%s" % (complex_id, team_id),
            lambda: self._team_in_complex(team_id, complex_id),
        )

    def commander_session(self, cookie: Optional[str]) -> Optional[dict]:
        """The commander payload behind a raw cookie, or None -- also None
        for a מכלול the operator suspended or deleted."""
        session = read_commander(self._secret, cookie)
        if session is None:
            return None
        if self._complex_active is not None and not self._cached(
            "c:%s" % session["complex_id"],
            lambda: self._complex_active(session["complex_id"]),
        ):
            return None
        return session

    def commander(self):
        """The commander of a מכלול (D43), on their own cookie."""
        def dependency(
            pakash_commander: Optional[str] = Cookie(
                default=None, alias=COMMANDER_COOKIE_NAME
            )
        ) -> dict:
            session = self.commander_session(pakash_commander)
            if session is None:
                raise AuthError("נדרשת התחברות של מפקד מכלול")
            return session
        return dependency

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
        # A commander inside a workplace (D43): the team must still be one
        # of theirs. Unlinking it ends the access on the next request.
        if session.get("commander") and not self.commander_reaches(
            session["team_id"], session["commander"]
        ):
            raise AuthError(UNLINKED_MESSAGE)
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

    def own_manager(self):
        """The workplace's own manager -- a boss session that is not a
        commander's. For the few things that are the manager's alone: their
        password, and reading what the commander changed (D43)."""
        def dependency(session: dict = Depends(self.boss())) -> dict:
            if session.get("commander"):
                raise ForbiddenError("הפעולה שמורה למפקד המשמרת")
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
            if session.get("commander"):
                # One conversation set per commander per workplace, the same
                # from any browser they sign in on (D43).
                return dict(
                    session, manager_id="commander-" + session["commander"]
                )
            owner = read(self._secret, pakash_manager)
            if not owner or owner.get("team_id") != session["team_id"] \
                    or not owner.get("manager_id"):
                owner = dict(session, manager_id=secrets.token_urlsafe(24))
                response.set_cookie(
                    MANAGER_COOKIE_NAME,
                    issue(self._secret, session["team_id"], ROLE_BOSS, 365,
                          manager_id=owner["manager_id"]),
                    httponly=True, samesite="lax", max_age=365 * 86400,
                    path="/",
                )
            return dict(session, manager_id=owner["manager_id"])
        return dependency


__all__ = ["Guards", "SUSPENDED_MESSAGE", "UNLINKED_MESSAGE"]
