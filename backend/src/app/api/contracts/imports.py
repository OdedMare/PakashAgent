"""Importing the workplace's own spreadsheets (D7)."""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.api.contracts.employee import ReadAssignment


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
