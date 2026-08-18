"""Workspace decisions: who may open a team, and in which role.

The repository owns the SQL and `common/sessions.py` owns the signing; this
owns the rules between them -- what a boss is allowed to do that a member is
not, and what a freshly created workspace inherits.
"""

from typing import List, Optional

from app.common.errors import AgentError, ConflictError
from app.common.sessions import ROLE_BOSS, ROLE_MEMBER

# Short enough to type on a phone, long enough not to fall to a guess in the
# time it takes anyone to notice. The boss picks it once and shares it with
# nobody -- members get a link instead.
_MIN_PASSWORD = 6
_MAX_PASSWORD = 200
_MAX_NAME = 80


class WorkspaceService:
    def __init__(self, repository):
        self._repository = repository

    def create(self, name: str, password: str) -> dict:
        """Open a workspace and return it with a boss session.

        The first team created also adopts any interview recorded before
        workspaces existed -- see `claim_orphan_sessions`. Without that, an
        existing install's finished interview becomes unreachable the moment
        every read starts filtering by team.
        """
        clean_name = (name or "").strip()
        if not clean_name:
            raise AgentError("שם הצוות אינו יכול להיות ריק")
        if len(clean_name) > _MAX_NAME:
            raise AgentError("שם הצוות ארוך מדי")
        self._validate_password(password)
        team = self._repository.create_team(clean_name, password)
        claimed = self._repository.claim_orphan_sessions(team["id"])
        result = _public(team, role=ROLE_BOSS)
        result["claimed_sessions"] = claimed
        return result

    def login(self, team_id: str, password: str) -> dict:
        """Verify the boss password. Raises `AuthError` if it does not match."""
        team = self._repository.authenticate_boss(team_id, password)
        return _public(team, role=ROLE_BOSS)

    def open_member_link(self, token: str) -> dict:
        """Resolve a share link to its team, as a member.

        Never returns the member token itself, even though it was just used
        to get here: the member area has no reason to re-render the link, and
        not putting it in a response body keeps it out of browser history,
        logs, and copy-pasted screenshots.
        """
        team = self._repository.team_by_member_token(token)
        return _public(team, role=ROLE_MEMBER, include_token=False)

    def list_teams(self) -> List[dict]:
        """Names and ids only -- this is served before anyone has logged in."""
        return [
            {"id": row["id"], "name": row["name"]}
            for row in self._repository.list_teams()
        ]

    def describe(self, team_id: str, role: str) -> dict:
        """The workspace as the current visitor is allowed to see it.

        The member token is part of a boss's view (it is the link they hand
        out) and absent from a member's, so the response shape is decided by
        the role rather than by which screen happens to be asking.
        """
        team = self._repository.get_team(team_id)
        view = _public(team, role=role, include_token=(role == ROLE_BOSS))
        view["profile"] = self._repository.team_profile(team_id)
        return view

    def rotate_member_link(self, team_id: str) -> dict:
        """Revoke the outstanding share link and mint a new one."""
        team = self._repository.rotate_member_token(team_id)
        return _public(team, role=ROLE_BOSS)

    def change_password(
        self, team_id: str, current: str, replacement: str
    ) -> None:
        """Re-verifies the current password first.

        A live session is not sufficient authority to change the credential
        it was issued from -- otherwise an unattended logged-in browser is a
        permanent takeover rather than a temporary one.
        """
        self._repository.authenticate_boss(team_id, current)
        self._validate_password(replacement)
        if current == replacement:
            raise ConflictError("הסיסמה החדשה זהה לנוכחית")
        self._repository.set_password(team_id, replacement)

    def _validate_password(self, password: str) -> None:
        value = password or ""
        if len(value) < _MIN_PASSWORD:
            raise AgentError(
                "הסיסמה חייבת להכיל לפחות %d תווים" % _MIN_PASSWORD
            )
        if len(value) > _MAX_PASSWORD:
            # Bounded because scrypt hashes whatever it is handed: an
            # unbounded password is an unbounded amount of work per login.
            raise AgentError("הסיסמה ארוכה מדי")


def _public(team: dict, role: str, include_token: bool = True) -> dict:
    """The safe projection of a team row.

    Built by naming what goes IN rather than deleting what must stay out --
    `password_hash` lives in the same row, and a blacklist is one added
    column away from leaking it.
    """
    view = {
        "id": team["id"],
        "name": team["name"],
        "role": role,
        "member_token": team["member_token"] if include_token else None,
    }
    return view


__all__ = ["WorkspaceService"]
