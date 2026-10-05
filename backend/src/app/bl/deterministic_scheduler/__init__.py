"""Fast, deterministic assignment of people into an existing slot grid.

**Not wired into generation.** The model assigns and `scheduler` bounds what
it returns (D3); an outage parks the job for a person to resume rather than
quietly building a schedule the model never saw. This package is kept as a
worked reference for that arithmetic -- the same inputs always produce the
same schedule -- and is covered by its own tests.
"""

import time
from typing import List, Optional

from app.bl import rotation
from app.bl.deterministic_scheduler.plan import DayPlan
from app.bl.deterministic_scheduler.rows import text
from app.bl.scheduler import build_slots
from app.common.errors.errors import AgentError

_SUMMARY = "השיבוץ נבנה בקוד לפי זמינות, כשירות, עומס וסבבים מחייבים."


def generate_day(
    profile: dict,
    day: str,
    availability: Optional[List[dict]] = None,
    history: Optional[List[dict]] = None,
    required_assignments: Optional[List[dict]] = None,
    already_scheduled: Optional[List[dict]] = None,
    shift_names: Optional[List[str]] = None,
) -> dict:
    """Fill one date without a model call.

    Required rows are pins. Other rows on this date are rebuilt, while rows
    from previous dates participate in rest, hours and fairness checks.
    """
    started = time.monotonic()
    errors = rotation.configuration_errors(profile)
    if errors:
        raise AgentError(
            "לא ניתן לשבץ לפני השלמת הגדרת הסבבים והתלתונים: %s." % "; ".join(errors)
        )
    slots = build_slots(profile, day, day)
    wanted = {text(name) for name in shift_names or [] if text(name)}
    if wanted:
        slots = [slot for slot in slots if slot["shift_name"] in wanted]
    if not slots:
        return _result(day, started, [], [], [])
    plan = DayPlan(profile, day, slots, availability, already_scheduled)
    plan.pin(required_assignments)
    plan.fill(history)
    return _result(day, started, plan.slots, plan.final(), plan.notes, plan.warnings())


def _result(day, started, slots, assignments, notes, warnings=None) -> dict:
    warnings = warnings or []
    return {
        "slots": slots,
        "assignments": assignments,
        "notes": notes,
        "summary": _SUMMARY,
        "warnings": warnings,
        "metrics": {
            "date": day,
            "status": "complete" if slots else "skipped",
            "duration_ms": int((time.monotonic() - started) * 1000),
            "returned": len(assignments),
            "accepted": len(assignments),
            "rejected": 0,
            "warnings": len(warnings),
            "repaired": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "engine": "deterministic",
        },
    }


__all__ = ["generate_day"]
