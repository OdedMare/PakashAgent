"""Standing preferences the agent remembers (D21)."""

from typing import Optional

from pydantic import BaseModel, Field


class Preference(BaseModel):
    """One standing operational preference this workplace has taught the agent.

    Not a rule (D1/D2 govern those, and they stay the boss's sentences on the
    profile) and not a constraint (`availability` is what the audit counts).
    Standing context the agent reads before it proposes — and a `suggested`
    one is inert until the manager approves it.
    """

    id: str
    kind: str = "general"
    subject: str = ""
    text: str
    evidence: str = ""
    status: str = "active"
    source: str = "manager"


class PreferenceRequest(BaseModel):
    """Record a preference, or propose one for the manager to approve."""

    text: str = Field(min_length=1, max_length=500)
    kind: str = Field(default="general", max_length=40)
    subject: str = Field(default="", max_length=120)
    evidence: str = Field(default="", max_length=500)
    # True stores it as `suggested`, which changes nothing until approved.
    suggested: bool = False


class PreferenceUpdate(BaseModel):
    """Reword a preference, approve a suggested one, or archive it."""

    text: Optional[str] = Field(default=None, max_length=500)
    status: Optional[str] = Field(default=None, max_length=20)
