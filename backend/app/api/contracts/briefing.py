"""Copilot permissions."""

from pydantic import BaseModel, Field


class CopilotPermissionUpdate(BaseModel):
    """How independently one class of copilot action may operate."""

    mode: str = Field(pattern="^(observe|suggest|auto)$")
