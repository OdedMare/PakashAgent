"""Route guards: who is asking, and may they.

FastAPI dependencies rather than middleware, so a route's signature states
its own access requirement -- `session: dict = Depends(deps.boss)` is visible
at the route, where a middleware rule matched on a path prefix is not, and a
new route added under the wrong prefix would silently inherit the wrong one.
"""

from fastapi import Cookie, Depends
from typing import Optional

from app.common.errors import AuthError
from app.common.sessions import (
    COOKIE_NAME, ROLE_BOSS, ROLE_EMPLOYEE, read,
)


class Guards:
    """Dependency factories bound to the process's signing secret."""

    def __init__(self, secret: str):
        self._secret = secret

    def visitor(self):
        """Any authenticated visitor -- boss, member, or employee."""
        def dependency(
            pakash_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME)
        ) -> dict:
            session = read(self._secret, pakash_session)
            if session is None:
                raise AuthError("נדרשת התחברות")
            return session
        return dependency

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


__all__ = ["Guards"]
