"""Reading a schedule the workplace already had, without a template.

[D7](../../../../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms):
there is no fixed template. The two real files in `FILE_FORMATS.md` are
structurally different — one is shift-major with dates across the top, the
other person-major with a nested `date x shift` header — so what is inferred
is **axis semantics**: which axis carries time, whether shift is nested under
date, and whether the non-time lanes are shifts or people.

**Nothing here persists anything**, and it is handed no repository: inference
produces an interpretation the manager approves, and only then does
`schedule_service` write. **No model call either** — layout inference is grid
arithmetic, and code that counts cannot hallucinate a person into a shift.

| Module | Owns |
|---|---|
| `files.py` | `.xlsx` / `.docx` into grids |
| `cells.py` | Reading one cell: dates, names, markers, hours |
| `vocabulary.py` | Matching headers against the declared shifts (D9) |
| `headers.py` | Date rows, nested headers, lane labels |
| `layouts.py` | One reader class per layout |
| `inference.py` | `infer()`: scoring the layouts against each other |
| `interpretation.py` | What the manager confirms |
"""

from app.bl.importer.files import read_grid, read_grids
from app.bl.importer.inference import infer
from app.bl.importer.interpretation import Interpretation

__all__ = ["Interpretation", "read_grid", "read_grids", "infer"]
