"""Building a period: generated, day by day, or blank (D18)."""

from typing import List, Optional

from pydantic import BaseModel, Field


class RequiredAssignment(BaseModel):
    """One manager-pinned placement that generation must preserve."""

    employee: str = Field(min_length=1, max_length=200)
    shift: str = Field(min_length=1, max_length=200)
    date: str = Field(min_length=1, max_length=20)


class GenerateRequest(BaseModel):
    """Build a period. Omitted dates mean the current week."""

    starts_on: Optional[str] = None
    ends_on: Optional[str] = None
    instructions: str = Field(default="", max_length=2000)
    required_assignments: List[RequiredAssignment] = Field(
        default=[], max_length=100
    )


class GenerateDayRequest(BaseModel):
    """Rebuild one date inside an existing draft."""

    date: str = Field(min_length=10, max_length=10)
    instructions: str = Field(default="", max_length=2000)


class BlankRequest(BaseModel):
    """Open an empty period for the manager to fill in by hand (D18).

    Same date arguments as `GenerateRequest` and deliberately no
    `instructions`: there is no model on this path to instruct.
    """

    starts_on: Optional[str] = None
    ends_on: Optional[str] = None
