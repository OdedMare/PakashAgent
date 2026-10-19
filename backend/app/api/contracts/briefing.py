"""The agent speaking first (D15), and copilot permissions."""

from typing import List

from pydantic import BaseModel, Field


class BriefingItem(BaseModel):
    """One thing the agent noticed on its own.

    `suggestion` is the sentence the manager could *send* to act on this —
    text for the composer, never a queued action. Nothing in a briefing is
    applied (D15).
    """

    text: str
    kind: str = "risk"
    suggestion: str = ""


class Briefing(BaseModel):
    """The agent speaking without being asked.

    `quiet` is the honest all-clear, and it is the common case by design: an
    agent that finds something urgent every time gets tuned out. A briefing
    that could not be produced at all arrives as `quiet` too, so the manager
    never sees an error where their calendar should be.
    """

    headline: str = ""
    items: List[BriefingItem] = []
    quiet: bool = True


class BriefingRequest(BaseModel):
    """Why the agent is being asked to speak, and what it already said.

    `last_said` is the recent headlines the browser is holding, sent back so
    the agent does not repeat an opening the manager already read. It lives
    in the client rather than a table because it is a property of this
    sitting, not of the workspace.
    """

    trigger: str = Field(default="opened", max_length=40)
    last_said: List[str] = Field(default=[], max_length=8)


class CopilotPermissionUpdate(BaseModel):
    """How independently one class of copilot action may operate."""

    mode: str = Field(pattern="^(observe|suggest|auto)$")
