"""Proposing and applying a change (D8/D12)."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from app.api.contracts.schedule import Warning


class ProposeRequest(BaseModel):
    """A change in the manager's own words. Applies nothing.

    `reason` carries the manager's reason when they volunteered it. When they
    did not, the agent asks rather than the request being rejected (D8).

    `pending_request` carries the request a previous turn could not carry out
    without guessing, echoed back from the `Proposal` that asked. It is what
    makes "ערב" a complete answer to "לאיזו משמרת?": the manager answers the
    question they were asked, and the original sentence is still here to
    answer it *about*. Sent by the client rather than held on the server —
    the alternative is per-manager conversation state on a stateless route,
    and a wrong or stale pending request would silently re-target a change.
    """

    request: str = Field(min_length=1, max_length=2000)
    schedule_id: Optional[str] = None
    reason: str = Field(default="", max_length=1000)
    pending_request: str = Field(default="", max_length=2000)


class Operation(BaseModel):
    """One concrete move inside a proposal."""

    action: str
    employee: str
    shift: str = ""
    date: str
    reason: str = ""
    with_employee: str = ""
    with_shift: str = ""
    with_date: str = ""


class ProfileOperation(BaseModel):
    """One proposed edit to the roster or shift vocabulary."""

    action: str
    target: str = ""
    item: Dict[str, Any]


class Proposal(BaseModel):
    """What the agent would do, and why. Nothing has been applied.

    `needs_reason` true means the manager was asked for their reason and the
    proposal is deliberately empty until they give one.

    `needs_input` true means the agent could not tell *what* the request
    referred to — which person, shift or date — and asked. The proposal is
    empty for the same reason and in the same way, and `pending_request`
    carries the sentence to resume once the manager answers.
    """

    schedule_id: str = ""
    reply: str = ""
    needs_reason: bool = False
    needs_input: bool = False
    agent_reason: str = ""
    stated_reason: str = ""
    # The request this proposal is still waiting to carry out. Empty on a
    # finished proposal; set only alongside a question, so the client has
    # nothing stale to send back once the answer has landed.
    pending_request: str = ""
    operations: List[Operation] = []
    profile_operations: List[ProfileOperation] = []
    constraints: List[Dict[str, Any]] = []
    warnings: List[Warning] = []


class ApplyRequest(BaseModel):
    """Confirm a proposal. The manager's reason is required by now."""

    schedule_id: str = ""
    operations: List[Operation] = []
    profile_operations: List[ProfileOperation] = []
    reason: str = Field(default="", max_length=1000)
    agent_reason: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_kind(self):
        if self.profile_operations:
            return self
        if not self.schedule_id or not self.reason.strip():
            raise ValueError("schedule_id and reason are required")
        return self
