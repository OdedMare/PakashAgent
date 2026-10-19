"""Turning an uploaded `.xlsx` or `.docx` into rectangular grids of strings."""

import io
import zipfile
from typing import List, Tuple
from xml.etree import ElementTree

from app.bl.importer.cells import text
from app.common.errors import AgentError

# A sheet bigger than this is not a shift schedule. Bounded because every
# cell is visited several times during inference.
MAX_ROWS = 400
MAX_COLUMNS = 200
_MAX_FILE_BYTES = 20 * 1024 * 1024
_WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

Grid = List[List[str]]


def read_grid(data: bytes, filename: str = "") -> Grid:
    """A file's first sheet (or its first table) as a grid of strings."""
    return read_grids(data, filename)[0][1]


def read_grids(data: bytes, filename: str = "") -> List[Tuple[str, Grid]]:
    """Every usable worksheet/table in one upload.

    A workbook often opens on a summary or instructions tab while the real
    schedules live in the other tabs. Returning every sheet lets the caller
    infer each one independently; non-schedule tabs then become ordinary
    per-sheet failures instead of hiding the schedules behind them.
    """
    if not data:
        raise AgentError("הקובץ ריק")
    if len(data) > _MAX_FILE_BYTES:
        raise AgentError("הקובץ גדול מדי (עד 20MB לקובץ)")
    name = (filename or "").lower()
    if name.endswith(".docx"):
        return [("", _read_docx(data))]
    if name.endswith(".xls"):
        raise AgentError(
            "פורמט Excel הישן (.xls) אינו נתמך; "
            "שמור את הקובץ כ־.xlsx ונסה שוב"
        )
    return _read_xlsx_sheets(data)


def bounded(grid: Grid) -> Grid:
    return [row[:MAX_COLUMNS] for row in (grid or [])[:MAX_ROWS]]


def rectangular(grid: Grid) -> Grid:
    width = max((len(row) for row in grid), default=0)
    return [list(row) + [""] * (width - len(row)) for row in grid]


def _read_xlsx_sheets(data: bytes) -> List[Tuple[str, Grid]]:
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover - openpyxl is a hard dependency
        raise AgentError("קריאת קבצי אקסל אינה זמינה בשרת הזה")
    try:
        book = load_workbook(io.BytesIO(data), data_only=True)
    except Exception:
        raise AgentError("לא הצלחתי לפתוח את קובץ האקסל")
    sheets = [
        sheet for sheet in book.worksheets if sheet.sheet_state == "visible"
    ] or list(book.worksheets)
    found = []
    for sheet in sheets:
        grid = _sheet_grid(sheet)
        if any(any(cell for cell in row) for row in grid):
            found.append((sheet.title, grid))
    if not found:
        raise AgentError("קובץ האקסל ריק")
    return found


def _sheet_grid(sheet) -> Grid:
    """One worksheet, bounded before iteration rather than afterwards.

    Excel files frequently carry formatting down to row 1,048,576; iterating
    the reported dimensions first makes a visually tiny sheet need huge time
    and memory, so the limits belong at the read boundary.
    """
    grid = [
        [text(value) for value in row]
        for row in sheet.iter_rows(
            min_row=1, max_row=min(sheet.max_row, MAX_ROWS),
            min_col=1, max_col=min(sheet.max_column, MAX_COLUMNS),
            values_only=True,
        )
    ]
    for merged in sheet.merged_cells.ranges:
        _unmerge(grid, merged)
    return rectangular(grid)


def _unmerge(grid: Grid, merged) -> None:
    """Copy a merged range's value into every cell it covers.

    Merged ranges carry their value only in the top-left cell. Sample B's
    date header is merged across its shift sub-columns, so without this the
    nested header reads as a date followed by blanks.
    """
    top, left = merged.min_row - 1, merged.min_col - 1
    if top >= len(grid) or left >= len(grid[top]):
        return
    value = grid[top][left]
    if not value:
        return
    for row in range(top, min(merged.max_row, MAX_ROWS)):
        for column in range(left, min(merged.max_col, MAX_COLUMNS)):
            if row < len(grid) and column < len(grid[row]):
                grid[row][column] = value


def _read_docx(data: bytes) -> Grid:
    """The first table in a Word document, as a grid.

    Word writes a merged cell by repeating its content in each covered cell,
    which is the behaviour the nested header needs, for free. Kept to the
    narrowest thing that can work: find a table, read its cells.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except Exception:
        raise AgentError("לא הצלחתי לפתוח את קובץ הוורד")
    for table in root.iter(_WORD_NAMESPACE + "tbl"):
        grid = [
            [
                text("".join(
                    node.text or "" for node in cell.iter(_WORD_NAMESPACE + "t")
                ))
                for cell in row.iter(_WORD_NAMESPACE + "tc")
            ]
            for row in table.iter(_WORD_NAMESPACE + "tr")
        ]
        if grid:
            return rectangular(grid)
    raise AgentError("לא נמצאה טבלה במסמך")
