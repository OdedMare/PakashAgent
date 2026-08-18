"""Pydantic HTTP contracts. No business logic — shapes only."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.common.runtime_settings.normalizers import MASKED_SECRET


class AnswerRequest(BaseModel):
    """One answer from the boss.

    A clicked option and free text arrive on the same field: an option's
    `answer` is a full sentence, sent verbatim as the boss's own message, so
    the model reads a click and a typed reply identically. That is why the UI
    sends `answer` and never a label or an index — a bare "2" would be the
    ambiguity the prompt explicitly guards against.
    """

    content: str = Field(min_length=1, max_length=4000)


class Option(BaseModel):
    """A clickable answer. `label` captions the button, `answer` is sent."""

    label: str
    answer: str


class Question(BaseModel):
    """The single question a turn asks, with the agent's own recommendation."""

    question: str
    recommendation: str = ""
    why: str = ""
    options: List[Option] = []


class Message(BaseModel):
    """One turn in the thread as the UI replays it.

    `options` and `recommendation` are lifted out of `question` so a past
    assistant turn can re-render its buttons without the client reaching
    into a nested object that is null on half the rows.
    """

    role: str
    content: str
    question: Optional[Question] = None
    options: List[Option] = []
    recommendation: Optional[str] = None


class InterviewTurn(BaseModel):
    """One conversational turn, shaped like the reference `plan-chat` reply.

    `draft` is the profile so far and is present on every turn, so the
    summary panel fills in as the interview proceeds. `profile` stays null
    until the interview is confirmed complete — it is the durable result,
    while `draft` is a proposal that may still change.
    """

    session_id: str
    status: str
    reply: str = ""
    question: Optional[Question] = None
    resolved: List[str] = []
    open_points: List[str] = []
    awaiting_confirmation: bool = False
    ready: bool = False
    draft: Optional[Dict[str, Any]] = None
    turns: List[Message] = []
    profile: Optional[Dict[str, Any]] = None


class ModelsProbeRequest(BaseModel):
    """Unsaved LLM connection settings used to probe available models.

    Empty, omitted, or masked means "use the saved value", so the panel can
    check a typed base URL without the boss re-entering a stored API key.
    """

    llm_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None

    def override(self, name: str) -> Optional[str]:
        value = (getattr(self, name) or "").strip()
        return None if not value or value == MASKED_SECRET else value


class CreateTeamRequest(BaseModel):
    """A new workspace. The password bound here is the boss's."""

    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=6, max_length=200)


class LoginRequest(BaseModel):
    team_id: str = Field(min_length=1)
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeRequest(BaseModel):
    current: str = Field(min_length=1, max_length=200)
    replacement: str = Field(min_length=6, max_length=200)


class TeamSummary(BaseModel):
    """A team as the unauthenticated login picker sees it."""

    id: str
    name: str


class Workspace(BaseModel):
    """The signed-in workspace.

    `member_token` is present for a boss (it is the link they hand out) and
    None for a member, who has no reason to re-read the credential they
    arrived on.
    """

    id: str
    name: str
    role: str
    member_token: Optional[str] = None
    claimed_sessions: Optional[int] = None


class TeamView(Workspace):
    """A workspace plus the workplace profile its interview produced."""

    profile: Optional[Dict[str, Any]] = None


class Warning(BaseModel):
    """One advisory finding from `bl/audit.py`.

    Advisory is the whole contract: a response carrying warnings is still a
    200 and the schedule is still valid to display. `code` is machine
    readable so the UI can group them; `message` is the Hebrew the manager
    reads (D3).
    """

    code: str
    severity: str
    message: str
    employee: str = ""
    date: str = ""
    shift: str = ""
    details: Dict[str, Any] = {}


class Slot(BaseModel):
    """One shift on one date — the thing a person is assigned into."""

    id: str
    shift_name: str
    slot_date: str
    start_time: str = ""
    end_time: str = ""
    headcount: int = 1
    is_on_call: bool = False


class Assignment(BaseModel):
    """A person on a slot, with the agent's reason.

    `reason` is never empty: an assignment nobody can account for defeats D8,
    and the repository refuses to store one.
    """

    id: str
    employee: str
    shift: str
    date: str
    reason: str
    slot_id: str


class Schedule(BaseModel):
    """One living period (D4) — edited in place, never versioned."""

    id: str
    starts_on: str
    ends_on: str
    status: str
    slots: List[Slot] = []
    assignments: List[Assignment] = []
    warnings: List[Warning] = []
    notes: List[str] = []
    summary: str = ""


class SchedulePeriod(BaseModel):
    """A period in the picker, without its grid."""

    id: str
    starts_on: str
    ends_on: str
    status: str


class Constraint(BaseModel):
    """A recorded availability constraint.

    An empty `shift_name` covers the whole day. `source` says where the
    information came from — the manager, the agent, or the manager writing
    down what an employee told them. Employees never write here: they have no
    account at all (D5/D10).
    """

    id: str
    employee: str
    constraint_date: str
    shift_name: str = ""
    available: bool = False
    reason: str = ""
    source: str = "manager"


class ChangeEntry(BaseModel):
    """One append-only change-log row.

    Both reasons are present because they answer different questions: the
    manager's `reason` is why the change happened, `agent_reason` is why the
    agent chose this particular move (D8).
    """

    id: str
    action: str
    employee: str = ""
    replaced_employee: str = ""
    slot_date: Optional[str] = None
    shift_name: str = ""
    reason: str = ""
    agent_reason: str = ""
    created_at: Optional[str] = None


class ManagementOverview(BaseModel):
    """Everything the management area opens with, in one call.

    The roster, the vocabulary, the current period with its warnings, the
    constraints, and the recent history are read together, so they are
    fetched together — a half-loaded management screen is worse than a
    slightly slower one.
    """

    profile: Optional[Dict[str, Any]] = None
    employees: List[Dict[str, Any]] = []
    shifts: List[Dict[str, Any]] = []
    schedule: Optional[Schedule] = None
    periods: List[SchedulePeriod] = []
    availability: List[Constraint] = []
    changes: List[ChangeEntry] = []


class GenerateRequest(BaseModel):
    """Build a period. Omitted dates mean the current week."""

    starts_on: Optional[str] = None
    ends_on: Optional[str] = None
    instructions: str = Field(default="", max_length=2000)


class ProposeRequest(BaseModel):
    """A change in the manager's own words. Applies nothing.

    `reason` carries the manager's reason when they volunteered it. When they
    did not, the agent asks rather than the request being rejected (D8).
    """

    request: str = Field(min_length=1, max_length=2000)
    schedule_id: Optional[str] = None
    reason: str = Field(default="", max_length=1000)


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


class Proposal(BaseModel):
    """What the agent would do, and why. Nothing has been applied.

    `needs_reason` true means the manager was asked for their reason and the
    proposal is deliberately empty until they give one.
    """

    schedule_id: str = ""
    reply: str = ""
    needs_reason: bool = False
    agent_reason: str = ""
    stated_reason: str = ""
    operations: List[Operation] = []
    constraints: List[Dict[str, Any]] = []
    warnings: List[Warning] = []


class ApplyRequest(BaseModel):
    """Confirm a proposal. The manager's reason is required by now."""

    schedule_id: str = Field(min_length=1)
    operations: List[Operation]
    reason: str = Field(min_length=1, max_length=1000)
    agent_reason: str = Field(default="", max_length=2000)


class MoveRequest(BaseModel):
    """A confirmed drag on the calendar.

    The gesture is a proposal; this is what the confirmation dialog sends
    once the manager has given their reason. `reason` is required for the
    same purpose it is required of a spoken change — a dragged shift is still
    a change, and it still has to be explained (D8).
    """

    assignment_id: str = Field(min_length=1)
    shift_name: str = Field(min_length=1)
    slot_date: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=1000)
    agent_reason: str = Field(default="", max_length=2000)


class ConstraintRequest(BaseModel):
    """Record a constraint for an employee.

    `source` distinguishes the manager entering it, the agent recording it
    from a conversation, and the manager writing down what an employee
    reported out of band. Employees have no account and never write here.
    """

    employee: str = Field(min_length=1, max_length=120)
    constraint_date: str = Field(min_length=1)
    shift_name: str = Field(default="", max_length=120)
    available: bool = False
    reason: str = Field(default="", max_length=1000)
    source: str = "manager"
