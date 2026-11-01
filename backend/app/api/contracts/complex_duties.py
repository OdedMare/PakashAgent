"""What the מכלול commander sends about duties.

Shape only: names, ranges and weekdays are checked in Hebrew by
`bl/complex_duties/values.py`, which every caller goes through.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class DutyTypeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    seats: int = 1
    weight: int = 1
    days: List[str] = Field(default_factory=list, max_length=7)


class DutyTypePatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    seats: Optional[int] = None
    weight: Optional[int] = None
    days: Optional[List[str]] = Field(default=None, max_length=7)
    active: Optional[bool] = None


class DutyAssignRequest(BaseModel):
    duty_type_id: str = Field(min_length=1, max_length=80)
    team_id: str = Field(min_length=1, max_length=80)
    employee: str = Field(min_length=1, max_length=120)
    duty_date: str = Field(min_length=10, max_length=10)
    note: str = Field(default="", max_length=400)
