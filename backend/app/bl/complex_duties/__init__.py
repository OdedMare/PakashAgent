"""A מכלול's duties (תורנויות): set by its commander, a whole day each.

| Module | Owns |
|---|---|
| `service.py` | `ComplexDutyService`: duty types, assigning and cancelling, the shifts a duty collides with, the change log and the team's notice |
| `values.py` | Checking what the commander typed: names, seats, weights, weekdays, dates and spans |
| `planning.py` | `DutyPlanning`: the fair fill (suggest, then approve through `assign`) and the balance |
| `ledger.py` | `DutyLedger`: the מכלול read once -- soldiers, duties, shift dates, and what rules a soldier out of a day (leaving, a whole-day constraint, home on the cycle) |
| `fill.py` | **The fair fill, pure**: the fewest weighted duties first, then weekends, the whole load, no shift that day, the longest since the last duty |
| `balance.py` | **The balance, pure**: per soldier, per משמרת and per kind, and the spread |

The duty is blocked in the soldier's own team by `records.availability()`,
which projects it as a `duty` with no hours (`audit/constraints.py`).
"""

from app.bl.complex_duties.service import (
    ACTION_COMPLEX_DUTY, ACTION_COMPLEX_DUTY_CANCELLED, ACTION_COMPLEX_DUTY_RECORDED,
    ComplexDutyService,
)

__all__ = [
    "ACTION_COMPLEX_DUTY", "ACTION_COMPLEX_DUTY_CANCELLED",
    "ACTION_COMPLEX_DUTY_RECORDED", "ComplexDutyService",
]
