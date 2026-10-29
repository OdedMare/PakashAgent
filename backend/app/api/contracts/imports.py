"""Importing the workplace's own files (D7/D42): preview, then confirm."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ImportLayout(BaseModel):
    """A sheet's shape (`bl/importer/layout.py`). Indices are zero-based,
    in the sheet as oriented: with `dates_down`, `header` is a column."""

    orientation: str = Field(default="dates_across", max_length=20)
    header: int = Field(default=0, ge=0, le=400)
    shift_line: Optional[int] = Field(default=None, ge=0, le=400)
    label: Optional[int] = Field(default=None, ge=0, le=400)
    lanes: str = Field(default="shifts", max_length=20)
    first_line: Optional[int] = Field(default=None, ge=0, le=400)
    last_line: Optional[int] = Field(default=None, ge=0, le=400)
    unavailable: List[str] = Field(default=[], max_length=20)
    ignore: List[str] = Field(default=[], max_length=20)


class ImportOptions(BaseModel):
    """What the confirm screen sends back with the file on a re-read: the
    manager's corrections. All optional -- the first read sends none."""

    sheet: str = Field(default="", max_length=200)
    layout: Optional[ImportLayout] = None
    week_start: str = Field(default="", max_length=10)
    hint: str = Field(default="", max_length=500)
    # A name in the file -> the roster name it means; "" leaves it out.
    names: Dict[str, str] = Field(default={}, max_length=500)
    # A shift heading in the file -> the declared shift; "" leaves it out.
    shifts: Dict[str, str] = Field(default={}, max_length=100)
    use_model: bool = True


class ImportedRow(BaseModel):
    employee: str = Field(default="", max_length=200)
    shift: str = Field(default="", max_length=200)
    date: str = Field(min_length=1, max_length=20)
    reason: str = Field(default="", max_length=200)


class ImportPerson(BaseModel):
    name: str
    employee: str = ""
    status: str
    candidates: List[str] = []
    count: int = 0


class ImportShift(BaseModel):
    name: str
    shift: str = ""
    declared: bool = False
    count: int = 0


class ImportOverlap(BaseModel):
    id: str
    starts_on: str
    ends_on: str
    status: str


class ImportAlternative(BaseModel):
    layout: ImportLayout
    confidence: float
    explanation: str
    rows: int


class ImportPreview(BaseModel):
    """What a file holds. **Nothing has been stored** when this returns."""

    filename: str = ""
    sheets: List[str] = []
    sheet_name: str = ""
    layout: ImportLayout
    layout_source: str
    explanation: str = ""
    confidence: float = 0.0
    alternatives: List[ImportAlternative] = []
    sheet: List[List[str]] = []
    people: List[ImportPerson] = []
    shifts: List[ImportShift] = []
    dates: List[str] = []
    starts_on: str = ""
    ends_on: str = ""
    assumed_week: str = ""
    assignments: List[ImportedRow] = []
    unavailability: List[ImportedRow] = []
    overlaps: List[ImportOverlap] = []
    warnings: List[str] = []
    summary: str = ""


class ImportConfirmRequest(BaseModel):
    """The rows exactly as the manager approved them. `schedule_id` merges
    them into that draft; without it a new period is opened."""

    assignments: List[ImportedRow] = Field(max_length=5000)
    unavailability: List[ImportedRow] = Field(default=[], max_length=2000)
    schedule_id: Optional[str] = Field(default=None, max_length=64)
    filename: str = Field(default="", max_length=200)
