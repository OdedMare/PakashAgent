"""The management area's overview: constraints, history, statistics."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.api.contracts.schedule import Schedule, SchedulePeriod


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
