"""Advisory checks over a schedule. Pure Python, no LLM, never blocks.

This is the counterweight to [D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-):
the agent makes every scheduling decision, and code recomputes only the
things that are *countable* — hours, consecutive shifts, double-booking,
availability conflicts, unfilled slots. Arithmetic over a roster is the one
thing an LLM gets subtly wrong in a way that looks exactly like getting it
right, so it is the one thing that is not left to the model.

Everything here returns warnings. Nothing here rejects a schedule, rewrites
an assignment, or vetoes the agent. If this package ever grows a `raise` on a
rule violation or a return value the caller is expected to branch on before
saving, D3 has been reversed — re-read it before doing that.

| Module | Owns |
|---|---|
| `auditor.py` | `audit()`: runs every check, sorts the warnings |
| `checks/` | One class per countable fact |
| `staffing_rules.py` | The one answer to "how full is this slot" |
| `roster.py` | Rows with their weighted hours; the policy thresholds |
| `constraints.py` | Whether an assignment falls outside an availability |
| `reports.py` | `personal_summary`, `fairness`, `load_history` |
| `stats.py` | `shift_stats` for the control room's charts |
"""

from app.bl.audit.auditor import audit
from app.bl.audit.codes import (
    CONSECUTIVE,
    CROSS_ROTATION,
    DOUBLE_BOOKED,
    MISSING_COMMANDER,
    MISSING_ROLE,
    OVER_HOURS,
    OVERSTAFFED,
    SEVERITY_NOTICE,
    SEVERITY_WARNING,
    SHORT_REST,
    UNAVAILABLE,
    UNFILLED,
)
from app.bl.audit.constraints import constraint_conflicts
from app.bl.audit.reports import fairness, load_history, personal_summary
from app.bl.audit.staffing_rules import counts_toward_staffing, required_headcount
from app.bl.audit.stats import shift_stats

__all__ = [
    "audit", "personal_summary", "fairness", "load_history", "shift_stats",
    "counts_toward_staffing", "required_headcount", "constraint_conflicts",
    "OVER_HOURS", "CONSECUTIVE", "SHORT_REST", "DOUBLE_BOOKED",
    "UNAVAILABLE", "UNFILLED", "OVERSTAFFED", "MISSING_ROLE",
    "MISSING_COMMANDER", "CROSS_ROTATION",
    "SEVERITY_WARNING", "SEVERITY_NOTICE",
]
