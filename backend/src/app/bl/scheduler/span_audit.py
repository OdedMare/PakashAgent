"""Which audit findings belong to a span, and which a repair could fix."""

import time
from typing import Any, List, Optional

from app.bl.audit import (
    CONSECUTIVE,
    DOUBLE_BOOKED,
    MISSING_ROLE,
    MISSING_COMMANDER,
    OVER_HOURS,
    OVERSTAFFED,
    SHORT_REST,
    UNAVAILABLE,
    UNFILLED,
    audit,
)
from app.bl.scheduler.candidates import slot_id
from app.bl.scheduler.values import bounded

# Problems code can prove from the accumulated roster. The model gets one
# focused chance to repair the current span; a second bad answer stays visible
# as an audit warning instead of entering an unbounded model loop.
REPAIRABLE_WARNING_CODES = frozenset({
    CONSECUTIVE, DOUBLE_BOOKED, MISSING_ROLE, MISSING_COMMANDER, OVER_HOURS,
    OVERSTAFFED, SHORT_REST, UNAVAILABLE, UNFILLED,
})


def audit_for_span(
    assignments: List[dict], slots: List[dict], profile: dict,
    availability: List[dict], dates: set,
) -> List[dict]:
    """Every warning that belongs to the dates just generated.

    A finding carrying no date at all is kept: it is true of the period the
    span sits in, and the manager reads these beside the schedule.
    """
    warnings = audit(
        assignments,
        (profile or {}).get("shifts") or [],
        (profile or {}).get("employees") or [],
        availability=availability,
        profile=profile,
        slots=slots,
    )
    return [
        item for item in warnings
        if not item.get("date") or bounded(item.get("date")) in dates
    ]


def span_warnings(
    assignments: List[dict], slots: List[dict], profile: dict,
    availability: List[dict], candidates: dict, dates: set,
) -> List[dict]:
    """The subset a repair call could actually fix. Nothing else is worth one.

    **A finding with no date is not one of them.** `OVER_HOURS` is a weekly
    total produced by days already committed, and the repair instruction
    forbids touching earlier dates -- so asking is a call that cannot succeed.
    Before this, one person crossing their ceiling on a Wednesday bought a
    repair call on every remaining day of the week.
    """
    warnings = [
        item for item in audit_for_span(
            assignments, slots, profile, availability, dates
        )
        if item.get("code") in REPAIRABLE_WARNING_CODES
        and item.get("severity") == "warning"
        and bounded(item.get("date")) in dates
    ]
    fillable = _fillable(slots, candidates)
    return [
        item for item in warnings
        if item.get("code") != UNFILLED
        or fillable.get((item.get("shift"), bounded(item.get("date"))), False)
    ]


def _fillable(slots: List[dict], candidates: dict) -> dict:
    """Which slots have at least as many seat-filling candidates as seats.

    Asking for impossible coverage burns a call the model cannot answer; the
    honest outcome is an unfilled warning. Counted in people who actually
    fill a seat, so trainees do not make a short slot look fillable.
    """
    counting = {
        item["id"] for item in candidates["employees"]
        if item.get("counts_toward_staffing")
    }
    fillable = {}
    for index, slot in enumerate(slots, 1):
        available = [
            employee_id
            for employee_id in candidates["by_slot"].get(slot_id(index), [])
            if employee_id in counting
        ]
        fillable[(slot["shift_name"], slot["slot_date"])] = (
            len(available) >= int(slot.get("headcount", 1))
        )
    return fillable


def usage_of(answer: Any) -> dict:
    usage = answer.get("_usage") if isinstance(answer, dict) else None
    return usage if isinstance(usage, dict) else {}


def add_usage(first: dict, second: dict) -> dict:
    return {
        key: first.get(key, 0) + second.get(key, 0)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }


def metrics(
    day: str, started: float, status: str, returned: int = 0,
    accepted: int = 0, rejected: int = 0, warnings: int = 0,
    repaired: bool = False, usage: Optional[dict] = None,
    through: str = "",
) -> dict:
    usage = usage or {}
    return {
        "date": day,
        # The last date this call covered. Equal to `date` on a single day,
        # so a reader that only knows about days still reads it correctly.
        "through": through or day,
        "status": status,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "returned": returned,
        "accepted": accepted,
        "rejected": rejected,
        "warnings": warnings,
        "repaired": repaired,
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }
