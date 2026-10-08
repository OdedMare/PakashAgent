"""The operator console (D28): sign-in, and the teams it manages."""

from typing import Optional

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class AdminCreateTeamRequest(BaseModel):
    """A workspace opened by the operator on a team's behalf."""

    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=6, max_length=200)
    # None is "no cap".
    max_employees: Optional[int] = Field(default=None, ge=1, le=5000)
    notes: str = Field(default="", max_length=500)


class AdminUpdateTeamRequest(BaseModel):
    """A partial edit. Absent keys are untouched; `max_employees: null`
    removes the cap -- the router reads `exclude_unset` to tell them apart."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    max_employees: Optional[int] = Field(default=None, ge=1, le=5000)
    active: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class AdminPasswordRequest(BaseModel):
    password: str = Field(min_length=6, max_length=200)


class AdminDeleteRequest(BaseModel):
    """The team's name, typed back."""

    confirm_name: str = Field(min_length=1, max_length=80)


class AdminReleaseRequest(BaseModel):
    employee: str = Field(min_length=1, max_length=120)
