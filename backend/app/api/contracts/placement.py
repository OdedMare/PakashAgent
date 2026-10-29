"""Placement checks and the manual path's writes (D18), constraints."""

import datetime

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.contracts.schedule import Closure, Warning


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
    is_overlap: bool = False
    exit_pattern: str = ""
    rotation: str = ""
    closing: bool = False


class PlacementCheck(BaseModel):
    """What `bl/placement.py` makes of a proposed placement.

    Ordinary audit findings remain advisory (D3). A blocking operational duty
    is different: the person is already occupied, so `blocking` is true and
    every write path refuses the placement.
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


class DepartureRequest(BaseModel):
    """Take one person off the active roster, by hand.

    `effective_date` empty means today. `reason` is optional: it is recorded
    against every shift the departure vacates, and the log already says a
    manager did it.
    """

    employee: str = Field(min_length=1, max_length=120)
    effective_date: str = Field(default="", max_length=20)
    reason: str = Field(default="", max_length=1000)


class DeparturePeriod(BaseModel):
    id: str
    starts_on: str
    ends_on: str


class Departure(BaseModel):
    """What a departure vacates — before the click, and after it."""

    employee: str
    effective_date: str
    shifts: int
    published: List[DeparturePeriod]


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
    # Where the shift stood when it was dragged. A drag confirmed after
    # somebody else already moved it is refused (409) instead of moving it
    # again from wherever it went; empty skips the check (an older client).
    from_slot_id: str = ""


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
    constraint_type: Literal["availability", "duty"] = "availability"

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        if not value:
            return ""
        try:
            return datetime.time.fromisoformat(value).strftime("%H:%M")
        except ValueError:
            raise ValueError("השעה חייבת להיות בפורמט HH:MM")

    @model_validator(mode="after")
    def valid_duty(self):
        if self.constraint_type != "duty":
            return self
        if self.shift_name:
            raise ValueError("תורנות חוסמת לפי שעות ולא לפי שם משמרת")
        if not self.start_time or not self.end_time:
            raise ValueError("לתורנות חוסמת צריך לציין שעת התחלה ושעת סיום")
        if self.available or not self.is_hard:
            raise ValueError("תורנות היא תמיד זמן חסום וקשיח")
        return self
