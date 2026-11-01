"""A מכלול's duties (תורנויות): set by its commander, a whole day each.

| Module | Owns |
|---|---|
| `service.py` | `ComplexDutyService`: duty types, assigning and cancelling, the shifts a duty collides with, the change log and the team's notice |
| `values.py` | Checking what the commander typed: names, seats, weights, weekdays, dates and spans |

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
