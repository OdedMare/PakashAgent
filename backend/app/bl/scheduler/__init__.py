"""The slot grid, who may work when, and building a span (D34).

`Scheduler` translates what code cannot read on its own (through
`bl/directive_agent/`) and hands everything to the constraint solver
(`bl/solver/`). The grid, availability and rotation rows here are pure
arithmetic the solver, the audit and the board all share.

Stateless: a function of the profile plus the period it is handed.
`schedule_service` owns persistence. The one thing this refuses to do is
store an assignment without a reason (D8).

| Module | Owns |
|---|---|
| `scheduler.py` | `Scheduler`: translate, then solve; reports what was left out |
| `slots.py` | The slot grid and the spans a period is solved in |
| `availability.py`, `rotation_rows.py` | Who may work when |
| `directives.py` | Which sentences need translating; reading a translation |
| `quality.py`, `compare.py` | Quality/performance measurements and saved-result comparison |
| `values.py` | Small value readers |
"""

from app.bl.scheduler.availability import effective_availability
from app.bl.scheduler.scheduler import Scheduler
from app.bl.scheduler.slots import build_slots, plan_spans

__all__ = ["Scheduler", "build_slots", "effective_availability", "plan_spans"]
