"""Small, deterministic conversation contracts shared by proposals and approvals."""

import datetime
import re

from app.bl.audit.staffing_rules import required_headcount, seat_counts
from app.bl.tools.values import iso
from app.common.errors.errors import AgentError

GAP_CODES = frozenset({"unfilled", "missing_role", "missing_commander"})


class RejectedPlan(AgentError):
    """A malformed proposal the model can repair."""


class NeedsManager(AgentError):
    """An essential detail that cannot be inferred."""


def approval_text(content):
    normalized = re.sub(r"[\s,.!؟?]+", " ", content.strip()).strip()
    return normalized in {
        "כן", "כן תעשה", "כן תעשי", "כן תבצע", "תבצע", "תעשי", "מאשר",
        "מאשרת", "מאשר את התוכנית", "מאשרת את התוכנית", "החל שינויים",
    }


def exception_warnings(plan):
    return [row for row in plan.get("warnings") or []
            if row.get("severity", "warning") == "warning" and row.get("code") not in GAP_CODES]


def whole_day_request(content, profile):
    return bool(re.search(r"(?:תשבץ|תשבצי|שבץ|שבצי).*?(?:היום|מחר|יום\s|ראשון|שני|שלישי|רביעי|חמישי|שישי|שבת)", content)) \
        and not any(row.get("name") and row["name"] in content for row in profile.get("shifts") or [])


def coverage_preview(profile, slots, assignments, warnings):
    """Every requested slot, even when the model returned no placements for it."""
    counts = seat_counts(assignments, profile.get("employees") or [], profile)
    result = []
    for slot in slots:
        date, shift = iso(slot["slot_date"]), slot["shift_name"]
        required = required_headcount(profile.get("shifts") or [], shift,
                                      datetime.date.fromisoformat(date), slots)
        problems = [row["message"] for row in warnings
                    if iso(row.get("date")) == date and row.get("shift") == shift]
        assigned = counts.get((date, shift), 0)
        complete = required is not None and assigned >= required and not problems
        result.append(dict(date=date, shift=shift, required=required, assigned=assigned,
                           complete=complete, problems=problems,
                           start_time=slot.get("start_time") or "",
                           end_time=slot.get("end_time") or ""))
    return dict(complete=bool(result) and all(row["complete"] for row in result), slots=result)
