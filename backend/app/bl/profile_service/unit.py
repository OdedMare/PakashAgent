"""Validating the unit's staffing standard and each person's dated
qualifications (`audit/unit_policy.py`)."""

import datetime
from typing import Any, List, Optional

from app.bl.profile_service.validation import text, text_list
from app.common.errors import AgentError


def unit_policy(value: Any) -> dict:
    if not isinstance(value, dict):
        raise AgentError("תקן היחידה אינו תקין")
    result = {}
    weak = value.get("max_weak_per_shift")
    if weak is not None and weak != "":
        result["max_weak_per_shift"] = _count(weak, "מספר בעלי דירוג ג' במשמרת")
    days = value.get("qualification_validity_days")
    if days is not None and days != "":
        result["qualification_validity_days"] = max(1, _count(days, "תוקף הכשירות"))
    fallbacks = value.get("role_fallbacks") or {}
    if not isinstance(fallbacks, dict):
        raise AgentError("התפקידים החלופיים אינם תקינים")
    result["role_fallbacks"] = {
        text(role): [item for item in text_list(others) if item != text(role)]
        for role, others in fallbacks.items() if text(role) and isinstance(others, list)
    }
    overflow = value.get("weekly_shifts_overflow")
    if overflow is not None and overflow != "":
        result["weekly_shifts_overflow"] = min(7, _count(overflow, "החריגה המותרת במשמרות בשבוע"))
    for key in ("weekly_shifts", "weekly_shifts_regular",
                "weekly_shifts_officers", "weekly_shifts_ncos"):
        if value.get(key):
            result[key] = _limits(value[key])
    return result


def _limits(value: Any) -> dict:
    if not isinstance(value, dict):
        raise AgentError("מספר המשמרות בשבוע אינו תקין")
    result = {}
    for bound in ("min", "max"):
        if value.get(bound) is not None and value.get(bound) != "":
            result[bound] = min(14, _count(value[bound], "מספר המשמרות בשבוע"))
    if "min" in result and "max" in result and result["min"] > result["max"]:
        raise AgentError("מינימום המשמרות בשבוע גדול מהמקסימום")
    return result


def _count(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise AgentError("%s חייב להיות מספר" % label)
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise AgentError("%s חייב להיות מספר" % label)
    if number < 0:
        raise AgentError("%s אינו יכול להיות שלילי" % label)
    return number


# A soldier's own weekly shift limits, over their service type's
# (`audit/unit_policy.weekly_limits`). Blank is None: the team's numbers.
PERSON_LIMITS = (("min_weekly_shifts", "מינימום המשמרות בשבוע", 0),
                 ("max_weekly_shifts", "מקסימום המשמרות בשבוע", 1))


def person_fields(row: dict) -> dict:
    """Dated qualifications, normalised (absent stays absent), and the
    soldier's own weekly shift limits."""
    fields = {}
    if row.get("qualifications") is not None:
        fields["qualifications"] = qualifications(row.get("qualifications"))
    for key, label, least in PERSON_LIMITS:
        value = row.get(key)
        fields[key] = None if value is None or value == "" \
            else min(14, max(least, _count(value, label)))
    low, high = fields["min_weekly_shifts"], fields["max_weekly_shifts"]
    if low is not None and high is not None and low > high:
        raise AgentError("מינימום המשמרות בשבוע של %s גדול מהמקסימום" % (text(row.get("name")) or "החייל/ת"))
    return fields


def qualifications(value: Any) -> List[dict]:
    if not isinstance(value, list):
        raise AgentError("רשימת הכשירויות אינה תקינה")
    result, seen = [], set()
    for raw in value:
        if not isinstance(raw, dict) or not text(raw.get("role")):
            raise AgentError("לכל כשירות חייב להיות תפקיד")
        role, last = text(raw.get("role")), _date(raw.get("last_active"))
        if role in seen:
            continue
        seen.add(role)
        result.append({"role": role, "last_active": last})
    return result


def _date(value: Any) -> str:
    stated = text(value)
    if not stated:
        return ""
    try:
        return datetime.date.fromisoformat(stated).isoformat()
    except ValueError:
        raise AgentError("תאריך הפעילות האחרונה של כשירות חייב להיות בפורמט YYYY-MM-DD")


__all__ = ["PERSON_LIMITS", "person_fields", "qualifications", "unit_policy"]
