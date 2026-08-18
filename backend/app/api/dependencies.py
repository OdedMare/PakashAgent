"""Route guards: who is asking, and may they.

FastAPI dependencies rather than middleware, so a route's signature states
its own access requirement -- `session: dict = Depends(deps.boss)` is visible
at the route, where a middleware rule matched on a path prefix is not, and a
new route added under the wrong prefix would silently inherit the wrong one.
"""

from fastapi import Cookie, Depends
from typing import Optional

from app.common.errors import AuthError
from app.common.sessions import COOKIE_NAME, ROLE_BOSS, read


class Guards:
    """Dependency factories bound to the process's signing secret."""

    def __init__(self, secret: str):
        self._secret = secret

    def visitor(self):
        """Any authenticated visitor -- boss or member."""
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

        This is the single place D5 (employees are read-only) is enforced.
        Every mutating route depends on it, so a member's cookie -- which is
        issued by the share link and carries `role: member` -- cannot reach a
        write no matter which URL it is pointed at.
        """
        def dependency(session: dict = Depends(self.visitor())) -> dict:
            if session.get("role") != ROLE_BOSS:
                raise AuthError("הפעולה מותרת למנהל בלבד")
            return session
        return dependency


__all__ = ["Guards"]
