"""Starting a replacement search without holding its HTTP request open."""

from pydantic import BaseModel, Field


class ReplacementSearchRequest(BaseModel):
    employee: str = Field(min_length=1, max_length=120)
    starts_on: str = Field(min_length=10, max_length=10)
    ends_on: str = Field(default="", max_length=10)
    # The filter chosen before the search: which shift types the cover may
    # come from and which roles it may hold. Empty means everybody.
    from_shifts: list[str] = Field(default_factory=list, max_length=50)
    roles: list[str] = Field(default_factory=list, max_length=50)
