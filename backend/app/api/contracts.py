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
    # Where the row came from (D18): 'agent', 'manager' or 'imported'.
    # Defaulted rather than required so a schedule read from a database that
    # predates the column still parses -- everything before D18 was generated.
    source: str = "agent"


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
    # The id a manual assignment landed on, echoed back so the client can
    # tell "placed" from "was already there" -- the insert conflicts silently
    # on (slot, employee), so a double click is a success that changed
    # nothing. Empty on every other response.
    assigned: str = ""


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


class Coverage(BaseModel):
    """Filled seats against required seats.

    Counted in seats rather than slots, so a shift needing three people with
    two on it reads as two thirds covered instead of rounding up to "filled".
    Slots whose headcount the profile does not state are in neither half —
    an assumed denominator would make the percentage fiction.
    """

    required: int = 0
    assigned: int = 0
    unfilled_slots: int = 0
    percent: float = 100.0


class ShiftLoad(BaseModel):
    """One shift name's share of the period, in the workplace's own
    vocabulary (D9). Every declared shift appears, including ones nobody was
    put on — a missing bar reads as "no such shift" rather than "nobody
    scheduled"."""

    shift: str
    count: int = 0
    hours: float = 0.0
    is_on_call: bool = False


class DayLoad(BaseModel):
    """One date's headcount and hours. Days with nobody on them are present
    as zeros so the chart shows the gap instead of closing it up."""

    date: str
    weekday: str = ""
    count: int = 0
    hours: float = 0.0
    on_call: int = 0


class EmployeeLoad(BaseModel):
    """One person's load, with the counts behind the hours — so two people on
    equal hours who are not carrying an equal week are distinguishable."""

    employee: str
    hours: float = 0.0
    shifts: int = 0
    on_call: int = 0
    days: int = 0


class WarningCount(BaseModel):
    """How many audit findings of one code. A count, never a score: nothing
    totals these into a number that would rank one period against another."""

    code: str
    severity: str = "notice"
    count: int = 0


class ConstraintPressure(BaseModel):
    """How constrained the period was, and how often that was overridden.

    `honored` is the figure the warning list cannot give: a constraint the
    schedule respected produces no warning, so it leaves no trace there.
    """

    blocked: int = 0
    people: int = 0
    conflicts: int = 0
    honored: int = 0


class ShiftStats(BaseModel):
    """The period in numbers, for the control room's charts.

    Computed by `bl/audit.py` — the same arithmetic the warnings come from,
    so a chart and the warning beneath it can never disagree. Advisory like
    everything else that module produces: this reports what the period looks
    like and grades nothing (D3).
    """

    total_hours: float = 0.0
    total_shifts: int = 0
    people_working: int = 0
    coverage: Coverage = Coverage()
    by_shift: List[ShiftLoad] = []
    by_day: List[DayLoad] = []
    by_employee: List[EmployeeLoad] = []
    warning_counts: List[WarningCount] = []
    constraint_pressure: ConstraintPressure = ConstraintPressure()


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
    # The charts' numbers. Part of the same call as everything else here for
    # the reason stated above: the stats describe the schedule beside them,
    # and a panel that arrived separately would show figures for a period the
    # calendar had already moved past.
    stats: ShiftStats = ShiftStats()


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


class BlankRequest(BaseModel):
    """Open an empty period for the manager to fill in by hand (D18).

    Same date arguments as `GenerateRequest` and deliberately no
    `instructions`: there is no model on this path to instruct.
    """

    starts_on: Optional[str] = None
    ends_on: Optional[str] = None


class AssignRequest(BaseModel):
    """Place one person on one slot, by hand (D18).

    `reason` is optional here, unlike on a change: filling an empty cell
    takes nothing away from anybody, and requiring a justification per cell
    would make authoring a week by hand cost a dialog per shift. When the
    manager gives one it is stored as the row's reason; when they do not, the
    row still says plainly that a person placed it.
    """

    shift_name: str = Field(min_length=1, max_length=120)
    slot_date: str = Field(min_length=1, max_length=40)
    employee: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="", max_length=1000)
    schedule_id: Optional[str] = None


class UnassignRequest(BaseModel):
    """Take one person off a slot, by hand (D18)."""

    assignment_id: str = Field(min_length=1)
    reason: str = Field(default="", max_length=1000)
    schedule_id: Optional[str] = None


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


# -- the employee's own area (D14) -----------------------------------------
#
# Note what is absent from every request body below: the employee's name.
# It is taken from the signed session cookie instead, because a name in the
# body is a name the sender chooses -- and that would let any signed-in
# employee read a colleague's hours or submit a constraint as them.


class ClaimRequest(BaseModel):
    """Claim a roster name and set a personal passcode.

    Requires a valid share-link session to reach, and the name must be one
    the interview actually recorded — a free-text claim would let anyone
    holding the link invent an employee.
    """

    employee: str = Field(min_length=1, max_length=120)
    passcode: str = Field(min_length=4, max_length=200)


class EmployeeLoginRequest(BaseModel):
    """Sign in as a claimed identity."""

    employee: str = Field(min_length=1, max_length=120)
    passcode: str = Field(min_length=1, max_length=200)


class ConstraintSubmission(BaseModel):
    """An employee asking not to be scheduled (or offering to be).

    A *request*, not a constraint: it lands as pending, is invisible to
    `bl/audit.py`, and changes nothing until the manager approves it (D14).
    `reason` is the employee's own words — the context a manager otherwise
    never gets in writing.
    """

    constraint_date: str = Field(min_length=1)
    shift_name: str = Field(default="", max_length=120)
    available: bool = False
    reason: str = Field(default="", max_length=1000)


class RequestDecision(BaseModel):
    """The manager ruling on a submission.

    `reason` is required to reject and optional to approve — a rejection that
    says nothing is how a submission channel stops being used, while an
    approval speaks for itself.
    """

    reason: str = Field(default="", max_length=1000)


class ReleaseRequest(BaseModel):
    """Free a claimed name so it can be claimed again.

    The manager's tool for someone who left or lost their passcode. Rotating
    the share link does not do this — the link and the claim are separate
    credentials.
    """

    employee: str = Field(min_length=1, max_length=120)
