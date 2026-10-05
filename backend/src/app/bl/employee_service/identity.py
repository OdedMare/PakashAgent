"""Claiming a roster name, and the manager's view of who has."""

from typing import List

from app.bl.employee_service.values import roster_names
from app.common.errors.errors import AgentError


class IdentityService:
    def __init__(self, repository):
        self._repository = repository

    def roster(self, team_id: str) -> dict:
        """Names available to claim, and which are taken.

        Served to a share-link visitor before they have an identity, so it
        carries names only -- never a passcode hash, never a last-seen time.
        """
        profile = self._repository.team_profile(team_id) or {}
        claimed = set(self._repository.claimed_names(team_id))
        return {
            "names": [
                {"employee": name, "claimed": name in claimed}
                for name in roster_names(profile)
            ]
        }

    def claim(self, team_id: str, employee: str, passcode: str) -> dict:
        """Bind a roster name to a passcode.

        The name is checked against the workplace profile first. Without that
        check the share link becomes a licence to create people, and every
        later join on that string would quietly match nothing.
        """
        name = (employee or "").strip()
        profile = self._repository.team_profile(team_id) or {}
        if name not in roster_names(profile):
            raise AgentError("השם אינו מופיע ברשימת העובדים של הצוות")
        self._repository.claim_identity(team_id, name, passcode)
        return {"employee": name}

    def login(self, team_id: str, employee: str, passcode: str) -> dict:
        """Verify a claim. Raises `AuthError` when it does not match."""
        row = self._repository.authenticate_employee(team_id, employee, passcode)
        return {"employee": row["employee"]}

    def identities(self, team_id: str) -> List[dict]:
        """Every claim, for the manager's roster panel."""
        return self._repository.list_identities(team_id)

    def release(self, team_id: str, employee: str) -> None:
        """Free a claimed name. The manager's tool for a departure."""
        self._repository.release_identity(team_id, employee)
