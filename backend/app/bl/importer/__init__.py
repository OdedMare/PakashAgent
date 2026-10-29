"""Reading a schedule the workplace already had, in whatever shape it has.

There is no template (D7), and since D42 there is no class per shape
either. A sheet's shape is a `Layout` -- which way time runs, which line
holds the dates, whether shifts are nested under them, what a lane is --
and one reader reads any sheet given one. Detection tries every plausible
layout and scores each by how much it explains in the workplace's own
terms; the model is asked to describe the layout only when detection is
unsure; the manager can correct it on the confirm screen. All three are
read by the same code, so the model never says who works when.

**Nothing here persists anything**, and it is handed no repository: the
interpretation is what the manager approves, and only then does
`schedule_service/importing.py` write.

| Module | Owns |
|---|---|
| `files.py` | `.xlsx` / `.docx` / `.csv` into grids |
| `cells.py` | Reading one cell: dates, weekdays, names, markers, hours |
| `vocabulary.py` | Matching headings against the declared shifts (D9) |
| `layout.py` | `Layout`: a sheet's shape as data, and orienting the grid |
| `headers.py` | Header lines: dates, weekday templates, lane labels |
| `reader.py` | `read()`: any sheet against any layout |
| `roster.py` | Which roster person a name in the file means |
| `detect.py` | Every plausible layout, read and scored |
| `mapper.py` | `LayoutMapper`: the model describing a layout, never the rows |
| `interpretation.py` | The rows to store, with the manager's name and shift mapping |
| `inference.py` | `infer()`: manager, detection, then the model |
"""

from app.bl.importer.files import read_grids
from app.bl.importer.inference import infer
from app.bl.importer.mapper import LayoutMapper

__all__ = ["LayoutMapper", "infer", "read_grids"]
