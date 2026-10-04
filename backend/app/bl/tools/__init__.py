"""The named questions the agent may ask about the team or schedule.

**Pure Python. No LLM call anywhere in this package.** Every tool is
arithmetic or a filter over state the board already renders: the model
chooses *which* question to ask and how to say the answer in Hebrew, while
what the answer *is* comes from here
([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

Asking "who can replace יוסי this weekend" of a model handed the whole period
means four countable things in one turn from a wall of JSON. So the questions
are named, and each one is answered by code.

**None of them writes.** The package is handed a repository and uses it for
reads only; the write path stays `schedule_service.apply()` behind the
manager's confirmation (D8/D12/D19). **Every tool takes `team_id` first**,
from the caller's signed session, never from the model (D10). **Errors are
values**: an unknown employee is `found: False` in Hebrew, not an exception.

| Module | Owns |
|---|---|
| `schedule_tools.py` | `ScheduleTools`: the menu and the dispatcher |
| `period_tools.py` | `team_overview`, `read_period`, `employee_state` |
| `coverage_tools.py` | `coverage_gaps`, `publish_readiness` |
| `placement_tools.py` | `validate_placement`, `find_replacements` |
| `profile_tools.py` | `profile_gaps` |
| `roster.py` | `resolve_employee`: one person, several, or none |
| `reads.py` | The shared repository reads |
"""

from app.bl.tools.names import (
    TOOL_COVERAGE_GAPS,
    TOOL_DESCRIPTIONS,
    TOOL_EMPLOYEE_STATE,
    TOOL_FIND_REPLACEMENTS,
    TOOL_NAMES,
    TOOL_PROFILE_GAPS,
    TOOL_PUBLISH_READINESS,
    TOOL_READ_PERIOD,
    TOOL_TEAM_OVERVIEW,
    TOOL_VALIDATE_PLACEMENT,
)
from app.bl.tools.roster import resolve_employee
from app.bl.tools.schedule_tools import ScheduleTools

__all__ = [
    "ScheduleTools", "resolve_employee", "TOOL_NAMES", "TOOL_DESCRIPTIONS",
    "TOOL_READ_PERIOD", "TOOL_TEAM_OVERVIEW", "TOOL_EMPLOYEE_STATE",
    "TOOL_COVERAGE_GAPS", "TOOL_VALIDATE_PLACEMENT", "TOOL_FIND_REPLACEMENTS",
    "TOOL_PUBLISH_READINESS", "TOOL_PROFILE_GAPS",
]
