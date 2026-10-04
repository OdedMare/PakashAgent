"""Which closure group is in, on any given date. Pure arithmetic, no model.

A closure (`סגירה`) is not another shift to balance: it is a stretch one group
holds, and balancing it away breaks the cycle everyone planned their month
around. So the cycle is computed here rather than asked of the model (D3).

The cycle is anchored, not inferred. `round` and `triplet` may each name their
own Saturday and first group; the legacy `first_closure_*` pair is a fallback.
Without an anchor there is no cycle, and nothing is guessed.

Four patterns: `round` (א, ב), `triplet` (תלתון: א, ב, ג), `hamshushim`
(from Thursday) and `shushim` (from Friday). Round and triplet set *who*
closes; the other two set *how long*. **A closure weekend runs Thursday to
Sunday morning** — the Sunday tail covers the day's first shift by the clock,
found from declared start times rather than a Hebrew name (D9).

| Module | Owns |
|---|---|
| `cycle.py` | One pattern's anchored cycle; configuration errors |
| `closures.py` | One person's closure days; the handover; `holds` |
| `views.py` | Per-date and per-weekend views |
| `vocabulary.py` | Groups, labels, patterns, date helpers |
"""

from app.bl.rotation.closures import closure_days, handover_shifts, holds
from app.bl.rotation.cycle import closing_group, configuration_errors, cycle
from app.bl.rotation.views import by_date, schedule_for_model
from app.bl.rotation.vocabulary import exit_pattern, label

__all__ = [
    "by_date", "closing_group", "closure_days", "configuration_errors",
    "cycle", "exit_pattern", "handover_shifts", "holds", "label",
    "schedule_for_model",
]
