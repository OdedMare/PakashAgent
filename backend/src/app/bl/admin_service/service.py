"""The operator console's rules: who is the operator, and what they may do.

The צוות משמרות זהב console (D28) is the only place a workspace is opened,
suspended or deleted. How many employees a team has is not here: that is the
team's manager's decision, made in their own roster. The repository owns the SQL and the
workspace service owns what a valid team name and password are; this owns
the rules between them -- that deleting asks for the team's name typed back,
that a suspension is refused for a team that does not exist, and that the
operator password is compared in constant time.
"""

import hmac
from typing import Any, Dict, List

from app.bl.workspace_service.service import validate_notes
from app.common.errors.errors import AgentError, AuthError, ForbiddenError

# Read from the runtime settings for the overview. Names only, never a key or
# a password: the overview is a glance, and the settings tab is where secrets
# are handled behind their mask.
_MODEL_FIELDS = (
    "llm_model", "llm_base_url", "llm_model_fast", "llm_model_default",
    "llm_model_advanced", "schedule_generation_mode",
)


class AdminService:
    def __init__(self, repository, workspace, password: str, store=None):
        self._repository = repository
        self._workspace = workspace
        self._password = password or ""
        self._store = store

    def login(self, given: str) -> None:
        """Verify the operator password. An unset one keeps the door shut."""
        if not self._password:
            raise ForbiddenError("מסוף הניהול נעול: לא הוגדרה סיסמה בשרת")
        if not hmac.compare_digest(
            (given or "").encode("utf-8"), self._password.encode("utf-8")
        ):
            raise AuthError("הסיסמה שגויה")

    def overview(self) -> dict:
        """Server-wide numbers, database reachability and the model in use."""
        try:
            totals = self._repository.admin_totals()
            database = "ok"
        except Exception:  # noqa: BLE001 -- the overview reports, never fails
            totals, database = {}, "error"
        settings = self._store.public() if self._store is not None else {}
        return {
            "totals": totals,
            "database": database,
            "model": {key: settings.get(key) or "" for key in _MODEL_FIELDS},
        }

    def teams(self) -> List[dict]:
        return self._repository.admin_teams()

    def team(self, team_id: str) -> dict:
        return self._repository.admin_team(team_id)

    def create(self, name: str, password: str) -> dict:
        """Open a workspace on a team's behalf and hand back its full row.

        A name and the first manager password, nothing more: everything
        inside the workspace -- the roster, how many people are on it, the
        shifts -- is the manager's to set up. The password is the operator's
        to set here and the team's to change later
        (`/api/workspace/password`), so the operator does not keep knowing it.
        """
        created = self._workspace.create(name, password)
        return self._repository.admin_team(created["id"])

    def update(self, team_id: str, patch: Dict[str, Any]) -> dict:
        """Rename, suspend/resume or annotate one team. Only the keys
        present are applied."""
        fields = {}  # type: Dict[str, Any]
        if "name" in patch:
            fields["name"] = self._workspace.validate_name(patch["name"])
        if "active" in patch:
            if not isinstance(patch["active"], bool):
                raise AgentError("מצב הצוות אינו תקין")
            fields["active"] = patch["active"]
        if "notes" in patch:
            fields["notes"] = validate_notes(patch["notes"])
        self._repository.update_team_admin(team_id, fields)
        return self._repository.admin_team(team_id)

    def reset_password(self, team_id: str, password: str) -> None:
        """Set a new manager password without knowing the old one.

        The operator's remedy for a manager who forgot theirs -- the one case
        `change_password`'s re-verification cannot serve.
        """
        self._workspace.validate_password(password)
        self._repository.get_team(team_id)
        self._repository.set_password(team_id, password)

    def rotate_link(self, team_id: str) -> dict:
        self._repository.rotate_member_token(team_id)
        return self._repository.admin_team(team_id)

    def release_identity(self, team_id: str, employee: str) -> dict:
        self._repository.release_identity(team_id, employee)
        return self._repository.admin_team(team_id)

    def delete(self, team_id: str, confirm_name: str) -> None:
        """Delete a workspace and everything in it, irreversibly.

        The team's name must be typed back. A button alone is one misclick
        from erasing a unit's whole history, and a dialog's "are you sure"
        is answered by reflex; retyping a name is not.
        """
        team = self._repository.get_team(team_id)
        if (confirm_name or "").strip() != team["name"].strip():
            raise AgentError("כדי למחוק יש להקליד את שם הצוות בדיוק")
        self._repository.delete_team(team_id)


__all__ = ["AdminService"]
