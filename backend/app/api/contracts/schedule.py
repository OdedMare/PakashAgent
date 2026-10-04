"""A schedule as the board reads it: slots, assignments, progress."""

from typing import Any, Dict, List

from pydantic import BaseModel


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
    """One checkpoint in a resumable date-range generation.

    A checkpoint covers a *span* of dates — one in `day` mode, up to a week
    in `week` mode. `date` remains its first date, so a reader that predates
    spans still sees what it always saw.
    """

    date: str
    # The span's last date, equal to `date` on a single-day checkpoint.
    through: str = ""
    # Every date this checkpoint covers, enumerated so progress is counted
    # in days rather than in model calls.
    dates: List[str] = []
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
    # How wide one model call is for this job: "day" or "week". Stamped when
    # the period is opened and never re-read, so a manager who changes the
    # setting mid-build is choosing how the *next* one runs rather than
    # re-planning the spans of a job already half checkpointed. Empty on a
    # job opened before the setting existed, which reads as "day".
    mode: str = ""
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
