"""Generate a schedule for a period. Every assignment carries its reason.

The model does the assigning; this package builds the slot grid it assigns
into, hands it the workplace and the constraints, and bounds what comes back.
It makes no scheduling decisions of its own
([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)) —
where it drops an assignment it is because the row is unusable (a person or a
shift nobody declared), never because it disagreed with the choice.

Stateless: a function of the profile plus the period it is handed.
`schedule_service` owns persistence, which is what lets the whole contract
here be tested against a fake model with no database. The one thing this
refuses to do is store an assignment without a reason (D8).

| Module | Owns |
|---|---|
| `scheduler.py` | `Scheduler`: the model call, and the legacy chunked path |
| `span.py` | One span: ask, verify, repair at most once |
| `request.py`, `repair.py` | Fixed context and focused, fully audited repairs |
| `planning.py`, `recovery.py` | Input budgets and smaller requests after capacity failures |
| `quality.py`, `compare.py` | Quality/performance measurements and saved-result comparison |
| `slots.py` | The slot grid, chunks and spans |
| `availability.py`, `rotation_rows.py` | Who may work when |
| `candidates.py` | Legal choices per slot and the id-pinned schema |
| `bounding.py` | Bounding model rows to what exists |
| `payload.py` | What the model is shown |
| `span_audit.py` | Which findings belong to a span; metrics |
"""

from app.bl.scheduler.availability import effective_availability
from app.bl.scheduler.payload import SCHEDULE_RESPONSE_SCHEMA
from app.bl.scheduler.scheduler import Scheduler
from app.bl.scheduler.slots import build_slots, plan_spans
from app.common.config.settings import GENERATION_MODES, MODE_DAY, MODE_WEEK

__all__ = [
    "Scheduler", "SCHEDULE_RESPONSE_SCHEMA", "build_slots",
    "effective_availability", "plan_spans",
    "GENERATION_MODES", "MODE_DAY", "MODE_WEEK",
]
