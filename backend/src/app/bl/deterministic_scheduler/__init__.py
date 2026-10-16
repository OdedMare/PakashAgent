"""Fast, deterministic assignment of people into an existing slot grid.

Wired into the selectable generation engine (D31). Structured requests run
here with zero model calls; automatic mode may first compile narrow semantic
instructions into validated availability or required-assignment rows. The
same inputs always produce the same schedule.
"""

import time
from typing import List, Optional

from app.bl import rotation
from app.bl.deterministic_scheduler.plan import DayPlan
from app.bl.deterministic_scheduler.rows import text
from app.bl.scheduler import build_slots
from app.bl.scheduler.quality import combine_metrics
from app.common.errors import AgentError

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
    plan = DayPlan(profile, day, slots, availability, already_scheduled, history)
    plan.pin(required_assignments)
    plan.fill(history)
    return _result(day, started, plan.slots, plan.final(), plan.notes, plan.warnings())


def unsupported_reason(profile, availability=None, instructions="", preferences=None) -> str:
    """Why code cannot faithfully represent this request, or an empty string."""
    if text(instructions):
        return "הבקשה כוללת הנחיה חופשית שרק מנוע ה-AI יכול לפרש"
    if preferences:
        return "לצוות יש העדפות מאושרות שמצריכות שיקול דעת של AI"
    if (profile or {}).get("rules"):
        return "לפרופיל יש כללים בשפה חופשית שמצריכים AI"
    if any((profile or {}).get(key) for key in (
        "dependencies", "casual_worker_policy", "rest_policy",
        "weekend_policy", "fairness_policy", "conflict_policy",
    )):
        return "לפרופיל יש מדיניות טקסטואלית שמצריכה AI"
    workplace = (profile or {}).get("workplace") or {}
    if workplace.get("general_exit_schedule"):
        return "תכנית היציאות הכללית כתובה בטקסט ומצריכה AI"
    training = (profile or {}).get("training_policy") or {}
    if training.get("shadow_shift_fraction") or training.get("shadow_shifts_per_week"):
        return "מדיניות החניכה מצריכה AI"
    for person in (profile or {}).get("employees") or []:
        if not isinstance(person, dict):
            continue
        if any(person.get(key) for key in (
            "notes", "availability", "workload", "trainers", "is_trainee",
        )):
            return "נתוני העובדים כוללים שיקול טקסטואלי או חניכה שמצריכים AI"
        recurring = person.get("recurring_constraints") or []
        if any(isinstance(item, str) or (
            isinstance(item, dict) and item.get("is_hard", True) is False
        ) for item in recurring):
            return "יש אילוץ חוזר טקסטואלי או רך שמצריך AI"
    if any(isinstance(item, dict) and item.get("is_hard", True) is False
           for item in availability or []):
        return "יש אילוץ זמינות רך שמצריך AI"
    return ""


def generate_span(
    profile: dict,
    starts_on: str,
    ends_on: str,
    availability: Optional[List[dict]] = None,
    history: Optional[List[dict]] = None,
    required_assignments: Optional[List[dict]] = None,
    already_scheduled: Optional[List[dict]] = None,
) -> dict:
    """Build any span as deterministic daily checkpoints with zero model calls."""
    slots = build_slots(profile, starts_on, ends_on)
    dates = sorted({slot["slot_date"] for slot in slots})
    committed = list(already_scheduled or [])
    result = {
        "slots": slots, "assignments": [], "notes": [], "warnings": [],
        "summary": _SUMMARY, "metrics": {},
    }
    for day in dates:
        pins = [row for row in required_assignments or [] if row.get("date") == day]
        current = generate_day(
            profile, day, availability=availability, history=history,
            required_assignments=pins, already_scheduled=committed,
        )
        committed = [row for row in committed if row.get("date") != day]
        committed.extend(current["assignments"])
        result["assignments"].extend(current["assignments"])
        result["notes"].extend(current.get("notes") or [])
        result["warnings"].extend(current.get("warnings") or [])
        result["metrics"] = combine_metrics(result["metrics"], current["metrics"])
    result["metrics"].update({
        "date": starts_on, "through": ends_on, "status": "complete",
        "accepted": len(result["assignments"]),
        "warnings": len(result["warnings"]), "engine": "code",
    })
    return result


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


__all__ = ["generate_day", "generate_span", "unsupported_reason"]
