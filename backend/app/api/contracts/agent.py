"""Asking and simulating (D19/D20)."""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.api.contracts.changes import Operation
from app.api.contracts.interview import Question
from app.api.contracts.schedule import Warning


class AskRequest(BaseModel):
    """A question about the schedule. **Answering it writes nothing.**

    Deliberately separate from `ProposeRequest`. A proposal is an answer with
    a confirm button attached; a question is a question, and offering a
    commitment in reply to *"who could cover Saturday"* would answer
    something the manager did not ask.
    """

    request: str = Field(min_length=1, max_length=500)
    schedule_id: Optional[str] = None
    # The question a previous turn asked about, echoed back so a one-word
    # answer resumes it instead of being read as a new question.
    pending_request: str = Field(default="", max_length=500)


class AgentStep(BaseModel):
    """One tool the agent ran while working out its answer.

    Returned so the manager can see which facts the answer rests on. This is
    a product requirement rather than debugging output: an answer whose
    checks are invisible is one that has to be taken on faith, and the whole
    point of deterministic tools is that it does not.
    """

    tool: str
    arguments: dict = {}
    ok: bool = True


class AgentAnswer(BaseModel):
    """What the agent made of a question. Carries no operations.

    There is no field here an `apply()` could read, which is the same
    property `Briefing` has and for the same reason: a surface that could
    write would reverse D3, D8 and D12 at once
    ([D15](../../docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).

    `used_model` says whether this came from the model or from the
    deterministic reader. Surfaced rather than hidden — the fallback answers
    a narrower set of questions, and saying so is what keeps that honest.
    """

    answer: str = ""
    steps: List[AgentStep] = []
    # Whether what is described would change the schedule. A label on a
    # sentence, not a queued change: the manager still sends it through
    # propose-then-confirm.
    needs_confirmation: bool = False
    # True when the agent is asking one focused follow-up rather than closing
    # the conversation with an answer.
    needs_input: bool = False
    # The FDE-style structured question. Options carry full answers, so a
    # click and a typed reply continue the same conversation identically.
    question: Optional[Question] = None
    # What the follow-up is a follow-up *to*. Set only beside a question, so
    # the manager's answer continues that request rather than replacing it.
    pending_request: str = ""
    used_model: bool = True
    understood: bool = True
    schedule_id: str = ""


class ToolRequest(BaseModel):
    """Run one named read-only tool directly."""

    tool: str = Field(min_length=1, max_length=60)
    arguments: dict = {}


class SimulateRequest(BaseModel):
    """Ask what a set of operations would do. **Persists nothing.**

    Takes `bl/changes.py`'s operation vocabulary so a simulation and the
    proposal it may become describe the change in one language.
    """

    operations: List[Operation] = []
    schedule_id: Optional[str] = None


class CoverageImpact(BaseModel):
    """Required against assigned, before and after the simulated change."""

    required: int = 0
    assigned_before: int = 0
    assigned_after: int = 0
    delta: int = 0
    percent_before: int = 100
    percent_after: int = 100


class WorkloadImpact(BaseModel):
    """One affected person's hours, before and after."""

    employee: str
    hours_before: float = 0.0
    hours_after: float = 0.0
    delta: float = 0.0


class SkippedOperation(BaseModel):
    """An operation the simulation could not apply, and why.

    Reported rather than dropped: the manager asked what would happen, and
    "that shift does not exist in this week" is the answer to that.
    """

    action: str = ""
    employee: str = ""
    shift: str = ""
    date: str = ""
    why: str = ""


class Simulation(BaseModel):
    """The period as a set of operations would leave it, computed in memory.

    **`simulated` is always true.** Stated in the payload so a client cannot
    mistake this for something that landed — the UI renders simulations in
    their own colour off the back of this field, visually distinct from a
    confirmed change.

    Approving one is an ordinary `POST /api/schedule/apply` with the
    manager's reason. There is no shortcut from here to a write
    ([D8](../../docs/DECISIONS.md#d8--two-reasons-both-required)).
    """

    simulated: bool = True
    applied: bool = False
    operations: List[Operation] = []
    skipped: List[SkippedOperation] = []
    introduced: List[Warning] = []
    resolved: List[Warning] = []
    warnings_after: List[Warning] = []
    coverage: CoverageImpact = CoverageImpact()
    workload: List[WorkloadImpact] = []
    affected: List[str] = []
    schedule_id: str = ""
