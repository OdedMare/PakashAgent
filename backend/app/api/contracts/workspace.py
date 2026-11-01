"""Teams, sign-in, and the workspace view."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CreateTeamRequest(BaseModel):
    """A new workspace. The password bound here is the boss's."""

    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=6, max_length=200)


class LoginRequest(BaseModel):
    team_id: str = Field(min_length=1)
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeRequest(BaseModel):
    current: str = Field(min_length=1, max_length=200)
    replacement: str = Field(min_length=6, max_length=200)


class Workspace(BaseModel):
    """The signed-in workspace.

    `member_token` is present for a boss (it is the link they hand out) and
    None for a member, who has no reason to re-read the credential they
    arrived on.
    """

    id: str
    name: str
    role: str
    member_token: Optional[str] = None


class TeamView(Workspace):
    """A workspace plus its saved workplace profile."""

    profile: Optional[Dict[str, Any]] = None
    # What a profile save names as `expected_revision` (see ProfileUpdate).
    profile_revision: Optional[int] = None
    # The מכלול this workplace belongs to, if any: {"id", "name"} (D43).
    complex: Optional[Dict[str, Any]] = None
    # True when the boss session is the commander's, not the manager's.
    commander: bool = False
