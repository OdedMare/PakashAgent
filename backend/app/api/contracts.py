"""Pydantic HTTP contracts. No business logic — shapes only."""

import datetime

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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
    mode: Literal["answer", "correction"] = "answer"


class InterviewSeed(BaseModel):
    """Facts read from an existing schedule before the interview starts."""

    workplace_name: str = Field(default="", max_length=120)
    source_files: List[str] = Field(default=[], max_length=100)
    employees: Dict[str, List[str]] = {}
    shifts: Dict[str, List[str]] = {}
    starts_on: str = Field(default="", max_length=10)
    ends_on: str = Field(default="", max_length=10)


class Option(BaseModel):
    """A clickable answer. `label` captions the button, `answer` is sent."""

    label: str
    answer: str


class Question(BaseModel):
    """The single question a turn asks, with the agent's own recommendation."""

    topic_id: str = ""
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
    mode: str = ""


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
    error: Optional[str] = None


class ModelsProbeRequest(BaseModel):
    """Unsaved LLM connection settings used to probe available models.

    Empty, omitted, or masked means "use the saved value", so the panel can
    check a typed base URL without the boss re-entering a stored API key.

    `role` says which saved connection those omissions fall back to. With
    roles free to sit on different providers, the general endpoint's
    catalogue is the wrong list for a role pointing somewhere else — so the
    panel probes per role, and a role whose fields are both empty is probed
    through the same fallback the client itself would use.
    """

    llm_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    role: Optional[str] = None

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
    requires_shift_manager: bool = False
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


class GenerationDay(BaseModel):
    """One checkpoint in a resumable date-range generation."""

    date: str
    status: str = "pending"
    attempts: int = 0
    error: str = ""
    metrics: Dict[str, Any] = {}


class GenerationProgress(BaseModel):
    """Persistent progress for a schedule produced one date at a time."""

    status: str = ""
    current_date: str = ""
    total_days: int = 0
    completed_days: int = 0
    failed_days: int = 0
    days: List[GenerationDay] = []
    # When a worker last said it was still on this job, UTC ISO-8601. Empty
    # on a job opened before this field existed, which the client reads as
    # "cannot tell" rather than as "stalled".
    heartbeat: str = ""
    # Whether the manager asked to stop. The worker checks it between days,
    # so a job can be `running` with this already true for as long as the
    # current model call takes to answer.
    cancel_requested: bool = False


class ScheduleProgress(BaseModel):
    """What the poller reads while a period is being built.

    Deliberately not a `Schedule`: the browser asks for this once a second,
    and the full period carries every slot, every assignment and a fresh
    audit over both. Progress is the counter, and the grid is fetched when
    the counter moves.
    """

    id: str
    status: str
    generation: GenerationProgress = GenerationProgress()


class ClosingGroup(BaseModel):
    """One group holding a closure, named the way the manager says it."""

    pattern: str = ""
    group: str = ""
    label: str = ""


class Closure(BaseModel):
    """Whose closure a date is — computed by `bl/rotation.py`, never guessed.

    `groups` empty means the rotation has nothing to say about this date: an
    ordinary weekday, or a workplace that never anchored its cycle. The two
    render the same way, because in both the honest answer is silence.

    `until_handover` marks the Sunday a closure ends on: the group is in for
    that morning and off for the rest of the day, so `shifts` names what the
    stretch still covers.
    """

    date: str = ""
    groups: List[ClosingGroup] = []
    label: str = ""
    employees: List[str] = []
    shifts: List[str] = []
    until_handover: bool = False


class Schedule(BaseModel):
    """One living period (D4) — edited in place, never versioned."""

    id: str
    starts_on: str
    ends_on: str
    status: str
    slots: List[Slot] = []
    assignments: List[Assignment] = []
    warnings: List[Warning] = []
    # Which dates in this period are somebody's closure. Computed once here
    # rather than in the browser: which group closes on 12/09 is arithmetic
    # (D3), and a second implementation of the cycle in TypeScript would
    # drift from the one the scheduler and the audit agree on.
    closures: List[Closure] = []
    notes: List[str] = []
    summary: str = ""
    generation: GenerationProgress = GenerationProgress()
    # The id a manual assignment landed on, echoed back so the client can
    # tell "placed" from "was already there" -- the insert conflicts silently
    # on (slot, employee), so a double click is a success that changed
    # nothing. Empty on every other response.
    assigned: str = ""
    # How many rows a clear actually removed, echoed for the same reason
    # `assigned` is: clearing an already-empty day is not a failure, and the
    # UI should say "nothing to clear" rather than report a change it did
    # not make. Zero on every other response.
    cleared: int = 0


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
    start_time: str = ""
    end_time: str = ""
    is_hard: bool = True
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


class ProfileUpdate(BaseModel):
    """A manual profile patch, including first-time setup without a model."""

    workplace: Optional[Dict[str, Any]] = None
    employees: Optional[List[Dict[str, Any]]] = None
    shifts: Optional[List[Dict[str, Any]]] = None
    rules: Optional[List[Dict[str, Any]]] = None
    dependencies: Optional[List[str]] = None
    training_policy: Optional[Dict[str, Any]] = None
    audit_policy: Optional[Dict[str, Any]] = None
    availability_process: Optional[str] = None
    constraint_deadline: Optional[str] = None
    casual_worker_policy: Optional[str] = None
    rest_policy: Optional[str] = None
    weekend_policy: Optional[str] = None
    fairness_policy: Optional[str] = None
    conflict_policy: Optional[str] = None
    existing_schedule_source: Optional[str] = None
    summary: Optional[str] = None


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
    employee: str = ""
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
        day_generation = bool(self.operations) and all(
            operation.action == "generate_day" for operation in self.operations
        )
        if not self.schedule_id or (not day_generation and not self.reason.strip()):
            raise ValueError("schedule_id and reason are required")
        return self


class BlankRequest(BaseModel):
    """Open an empty period for the manager to fill in by hand (D18).

    Same date arguments as `GenerateRequest` and deliberately no
    `instructions`: there is no model on this path to instruct.
    """

    starts_on: Optional[str] = None
    ends_on: Optional[str] = None


class CheckRequest(BaseModel):
    """Ask what a placement would cost, before making it. Writes nothing.

    `moving_assignment_id` is set when the manager is dragging an existing
    row rather than filling an empty cell: the row comes out of the
    hypothetical before the new one goes in, so a move is checked as a move
    and not as one person in two places at once.
    """

    employee: str = Field(default="", max_length=120)
    shift_name: str = Field(min_length=1, max_length=120)
    slot_date: str = Field(min_length=1, max_length=40)
    schedule_id: Optional[str] = None
    moving_assignment_id: str = Field(default="", max_length=64)


class AlternativeEmployee(BaseModel):
    """Somebody else who could take this slot cleanly."""

    employee: str
    hours: float = 0.0
    why: str = ""


class AlternativeSlot(BaseModel):
    """Somewhere else this same person could go, near the wanted date."""

    shift_name: str
    slot_date: str
    distance: int = 0
    why: str = ""


class Alternatives(BaseModel):
    """Deterministic ways out of a placement that warns. No model."""

    employees: List[AlternativeEmployee] = []
    slots: List[AlternativeSlot] = []


class PlacementCandidate(BaseModel):
    """One roster option for the selected slot, including why not.

    `rotation` and `closing` are what make a closure placeable by hand: the
    grid never says whose weekend a Thursday is, so a picker sorted only by
    hours would offer the group on exit first.
    """

    employee: str
    available: bool = True
    reasons: List[str] = []
    hours: float = 0.0
    is_shift_manager: bool = False
    can_train: bool = False
    rotation: str = ""
    closing: bool = False


class PlacementCheck(BaseModel):
    """What `bl/placement.py` makes of a proposed placement.

    **`blocking` is always false**, and it is stated rather than omitted so
    the contract itself says that refusing is not on the table: the audit
    advises and never gates
    ([D3](../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
    A manager may place somebody this reports on, and the write that follows
    will store it.
    """

    ok: bool = True
    blocking: bool = False
    reasons: List[str] = []
    warnings: List[Warning] = []
    eligible: bool = True
    alternatives: Alternatives = Alternatives()
    candidates: List[PlacementCandidate] = []
    closure: Closure = Closure()


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


class ClearRequest(BaseModel):
    """Empty one day's shifts, or the whole period's (D18).

    `slot_date` empty means the period. `reason` is optional for the reason
    `unassign`'s is: a manager clearing a day the agent just built is
    correcting an outcome rather than deciding about a person, and refusing
    the gesture without a sentence would strand the manual path halfway
    through. Every row that goes is still logged with where it came from.
    """

    slot_date: str = Field(default="", max_length=20)
    reason: str = Field(default="", max_length=1000)


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
    # Which period the drag happened on. Every other hand-write on the board
    # already carries this; `move` did not, and resolved "the current period"
    # server-side instead — so a drag on any week other than the one covering
    # today looked for the target slot in the wrong period and was refused.
    # Empty still means "the current period", which is what an older client
    # sends.
    schedule_id: str = ""


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
    start_time: str = Field(default="", max_length=5)
    end_time: str = Field(default="", max_length=5)
    is_hard: bool = True
    reason: str = Field(default="", max_length=1000)
    source: str = "manager"

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        if not value:
            return ""
        try:
            return datetime.time.fromisoformat(value).strftime("%H:%M")
        except ValueError:
            raise ValueError("השעה חייבת להיות בפורמט HH:MM")


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


class SwapProposal(BaseModel):
    """One employee offering another a trade of shifts.

    Both shifts are named by **assignment id**, not by date and shift name.
    The employee picks two cells off a grid they are already looking at, and
    ids mean the request can only ever name shifts that are really on the
    published schedule — a date-and-name pair could describe a slot that does
    not exist, or one belonging to somebody else.

    Nothing here moves an assignment. It lands awaiting the colleague's
    answer, and even their agreement only puts it in the manager's inbox
    (D14 — the manager remains the sole decider).
    """

    assignment_id: str = Field(min_length=1, max_length=64)
    counterparty: str = Field(min_length=1, max_length=120)
    counterparty_assignment_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=1000)


class SwapAnswer(BaseModel):
    """The colleague's reply to an offer.

    `agreed` false is a decline, which ends the swap — distinct from the
    manager's rejection, because which of the two people said no is a fact
    the requester needs in order to know whether to ask again.
    """

    agreed: bool


class ReleaseRequest(BaseModel):
    """Free a claimed name so it can be claimed again.

    The manager's tool for someone who left or lost their passcode. Rotating
    the share link does not do this — the link and the claim are separate
    credentials.
    """

    employee: str = Field(min_length=1, max_length=120)


class ReadAssignment(BaseModel):
    """One row as the importer read it, before anyone has confirmed anything.

    `shift` may be empty. A sheet of dates and people carries no shift
    information at all, and an empty name is how that absence stays visible
    instead of being silently answered with an invented one
    ([D9](../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
    The confirm screen is where the manager supplies it — which is why
    `ImportedAssignment`, the shape that comes *back*, requires it.
    """

    employee: str = Field(min_length=1, max_length=120)
    shift: str = Field(default="", max_length=80)
    date: str = Field(min_length=1, max_length=10)
    reason: str = Field(default="", max_length=1000)


class ImportedAssignment(BaseModel):
    """One row of an interpretation, as the manager approved it.

    Sent back from the confirm screen rather than re-read from the file, so a
    name the manager corrected there is what gets stored (D7). `shift` is
    required here even though the read shape allows it empty: by the time a
    row is being stored the question has been asked, and storing a shiftless
    assignment would put a row on the grid that no slot can hold.
    """

    employee: str = Field(min_length=1, max_length=120)
    shift: str = Field(min_length=1, max_length=80)
    date: str = Field(min_length=1, max_length=10)
    reason: str = Field(default="", max_length=1000)


class ImportedConstraint(BaseModel):
    """An unavailability the sheet stated outright.

    `employee` may be empty: a marker the file never attributed to anybody is
    reported as such rather than guessed at, and the confirm screen is where
    the name is supplied.
    """

    employee: str = Field(default="", max_length=120)
    date: str = Field(min_length=1, max_length=10)
    shift: str = Field(default="", max_length=80)
    reason: str = Field(default="", max_length=1000)


class CandidateRule(BaseModel):
    """A rule the history suggests, which the manager has not yet accepted.

    `approved` is always false on the way out — a candidate becomes a rule
    only by the manager saying so, never by having been proposed.
    """

    text: str
    kind: str
    evidence: str
    confidence: str
    approved: bool = False


class ImportedPeriod(BaseModel):
    """What one uploaded file was understood to say."""

    filename: str = ""
    layout: str
    shifts: List[str] = []
    people: List[str] = []
    dates: List[str] = []
    starts_on: str = ""
    ends_on: str = ""
    assignments: List[ReadAssignment] = []
    unavailability: List[ImportedConstraint] = []
    warnings: List[str] = []
    summary: str = ""


class ImportFailure(BaseModel):
    """A file that could not be read, reported beside the ones that could."""

    filename: str = ""
    error: str


class ImportPreview(BaseModel):
    """The interpretation the manager confirms before anything is stored.

    This response is the whole of [D7](../../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)
    at the HTTP boundary: producing it writes nothing, and `POST
    /api/schedule/import/confirm` is the only thing that persists.
    """

    periods: List[ImportedPeriod] = []
    failures: List[ImportFailure] = []
    observations: dict = {}
    candidate_rules: List[CandidateRule] = []
    notes: List[str] = []


class ImportConfirmRequest(BaseModel):
    """Store an interpretation the manager approved."""

    assignments: List[ImportedAssignment]
    unavailability: List[ImportedConstraint] = []
    starts_on: Optional[str] = None
    ends_on: Optional[str] = None


# -- asking, simulating, remembering ---------------------------------------


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
