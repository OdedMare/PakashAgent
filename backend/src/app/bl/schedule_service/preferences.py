"""What the workplace taught the agent, beyond one-off decisions (D21)."""

from typing import List, Optional

from app.common.errors import AgentError
from app.dal.repository.schedules import (
    PREFERENCE_ACTIVE,
    PREFERENCE_GENERAL,
    PREFERENCE_SUGGESTED,
    SOURCE_MANAGER,
)


class PreferenceService:
    def __init__(self, repository):
        self._repository = repository

    def preferences(
        self, team_id: str, status: Optional[str] = None
    ) -> List[dict]:
        return self._repository.preferences(team_id, status=status)

    def add_preference(
        self,
        team_id: str,
        text: str,
        kind: str = PREFERENCE_GENERAL,
        subject: str = "",
        evidence: str = "",
        suggested: bool = False,
        source: str = SOURCE_MANAGER,
    ) -> dict:
        """Remember an operational preference for this team.

        `suggested` is what separates the agent noticing something from the
        manager deciding it. A suggested row is inert: `ask()` reads only
        `active` ones, so a proposal changes nothing until it is approved —
        the same line D14 draws between a request and a constraint.
        """
        if not (text or "").strip():
            raise AgentError("צריך לכתוב את ההעדפה")
        return self._repository.create_preference(
            team_id,
            text=text,
            kind=kind,
            subject=subject,
            evidence=evidence,
            status=PREFERENCE_SUGGESTED if suggested else PREFERENCE_ACTIVE,
            source=source,
        )

    def update_preference(
        self,
        team_id: str,
        row_id: str,
        text: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict:
        """Reword a preference, approve a suggested one, or archive it.

        Approving is this call with `status='active'`, which is why approval
        needs no separate method.
        """
        return self._repository.update_preference(
            row_id, team_id, text=text, status=status
        )

    def delete_preference(self, team_id: str, row_id: str) -> None:
        self._repository.delete_preference(row_id, team_id)
