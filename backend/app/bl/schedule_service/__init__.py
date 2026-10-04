"""Persistence and orchestration around the schedule.

Two shapes are load-bearing here:

- **Propose and apply are separate calls.** A proposal writes nothing. The
  manager confirms in between, and only then does anything land
  ([D8](../../../../docs/DECISIONS.md#d8--two-reasons-both-required)). A drag
  on the calendar goes through exactly the same two steps as a sentence typed
  at the agent — the gesture is a proposal, not an edit.
- **Every response carrying a schedule carries its warnings.** They are
  advisory and never gate anything
  ([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)):
  a schedule with warnings is still a `200` and still renders.

| Module | Owns |
|---|---|
| `service.py` | The facade: wires collaborators, forwards calls |
| `context.py` | Shared reads: the audited view, the period in play |
| `reader.py` | Current period, overview, placement check |
| `generation/` | Opening a period, stepping and running a range job |
| `importing.py` | Import preview and commit (D7) |
| `manual.py` | The manual path (D18) |
| `changing.py`, `operations.py` | Propose / apply / move (D8/D12) |
| `constraints.py`, `preferences.py` | Constraints, history, preferences |
| `learning.py`, `patterns.py` | Repeated corrections as suggestions |
| `answering.py` | Tools and simulations (D19/D20) |
| `speaking.py` | Briefings (D15) and the workbook export (D17) |
"""

from app.bl.schedule_service.constants import (  # noqa: F401
    ACTION_ASSIGNED,
    ACTION_CONSTRAINT,
    ACTION_GENERATED,
    ACTION_IMPORTED,
    ACTION_MOVED,
    ACTION_OPENED,
    ACTION_PUBLISHED,
    ACTION_REMOVED,
    ACTION_SWAPPED,
    GENERATION_CANCELLED,
    GENERATION_COMPLETE,
    GENERATION_FAILED,
    GENERATION_HEARTBEAT_SECONDS,
    GENERATION_RUNNING,
    IMPORTED_REASON,
    MANUAL_REASON,
)
from app.bl.schedule_service.service import ScheduleService

__all__ = ["ScheduleService"]
