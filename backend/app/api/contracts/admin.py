"""The operator console (D28): sign-in, and the teams it manages."""

from typing import List, Optional

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class AdminCreateTeamRequest(BaseModel):
    """A workspace opened by the operator on a team's behalf: a name and the
    first manager password. The roster is the manager's to build."""

    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=6, max_length=200)


class AdminUpdateTeamRequest(BaseModel):
    """A partial edit. Absent keys are untouched -- the router reads
    `exclude_unset`, so only what was sent is applied."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    active: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class AdminPasswordRequest(BaseModel):
    password: str = Field(min_length=6, max_length=200)


class AdminDeleteRequest(BaseModel):
    """The team's name, typed back."""

    confirm_name: str = Field(min_length=1, max_length=80)


class AdminReleaseRequest(BaseModel):
    employee: str = Field(min_length=1, max_length=120)


class AdminCreateComplexRequest(BaseModel):
    """A מכלול (D43): its name, the commander's first password, and the
    existing workplaces it joins."""

    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=6, max_length=200)
    team_ids: List[str] = Field(default_factory=list, max_length=100)


class AdminUpdateComplexRequest(BaseModel):
    """A partial edit; `team_ids`, when sent, is the whole new membership."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    active: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=500)
    team_ids: Optional[List[str]] = Field(default=None, max_length=100)


class CommanderLoginRequest(BaseModel):
    complex_id: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)
