"""Validating the workplace block, its rotation anchors, rules and policies."""

import datetime
from typing import Any, List

from app.bl.profile_service.validation import text, text_list, valid_time
from app.common.errors.errors import AgentError

_OPTIONAL_EXIT_PATTERNS = ("triplet", "hamshushim", "shushim")
_GROUPS = {"round": ("א", "ב"), "triplet": ("א", "ב", "ג")}
_AUDIT_FIELDS = (
    ("max_weekly_hours", "מקסימום שעות בשבוע", 0),
    ("max_consecutive_days", "מקסימום ימים רצופים", 1),
    ("min_rest_hours", "מינימום מנוחה בין משמרות", 0),
)


def _check_date(value: str, message: str) -> None:
    if value:
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            raise AgentError(message)


def workplace(value: Any) -> dict:
    if not isinstance(value, dict):
        raise AgentError("פרטי היחידה אינם תקינים")
    result = dict(value)
    mode = text(result.get("rotation_mode")) or "round"
    if mode not in _GROUPS:
        raise AgentError("מבנה הסבב אינו תקין")
    first_group = text(result.get("first_closure_group")) or _GROUPS[mode][0]
    if first_group not in _GROUPS[mode]:
        raise AgentError("קבוצת הסגירה הראשונה אינה מתאימה למבנה הסבב")
    first_date = text(result.get("first_closure_date"))
    _check_date(first_date, "תאריך הסגירה הראשונה אינו תקין")
    result.update({
        "name": text(result.get("name")),
        "planning_horizon": text(result.get("planning_horizon")) or "שבוע",
        "operating_days": text_list(result.get("operating_days") or []),
        "rotation_mode": mode,
        "first_closure_group": first_group,
        "first_closure_date": first_date,
        "general_exit_schedule": text(result.get("general_exit_schedule")),
        "enabled_exit_patterns": _enabled_patterns(result),
        "rotation_a_unavailability": _rotation_rules(
            result.get("rotation_a_unavailability") or []
        ),
    })
    for pattern, groups in _GROUPS.items():
        _pattern_anchor(result, pattern, groups)
    return result


def _enabled_patterns(result: dict) -> List[str]:
    enabled = text_list(result.get("enabled_exit_patterns") or [])
    if any(pattern not in _OPTIONAL_EXIT_PATTERNS for pattern in enabled):
        raise AgentError("מבנה היציאות האופציונלי אינו תקין")
    return list(dict.fromkeys(enabled))


def _pattern_anchor(place: dict, pattern: str, groups: tuple) -> None:
    """Validate one optional cycle anchor without inventing the other one."""
    date_key = "%s_first_closure_date" % pattern
    group_key = "%s_first_closure_group" % pattern
    if date_key not in place and group_key not in place:
        return
    group = text(place.get(group_key)) or groups[0]
    if group not in groups:
        raise AgentError("קבוצת העוגן אינה מתאימה למחזור היציאות")
    date = text(place.get(date_key))
    _check_date(date, "תאריך העוגן של מחזור היציאות אינו תקין")
    place[group_key], place[date_key] = group, date


def _rotation_rules(value: Any) -> List[dict]:
    """Rotation A uses the same shape as recurring employee constraints."""
    if not isinstance(value, list):
        raise AgentError("זמני אי־הזמינות של סבב א׳ אינם תקינים")
    result = []
    for raw in value:
        if not isinstance(raw, dict):
            raise AgentError("פרטי אי־הזמינות של סבב א׳ אינם תקינים")
        start, end = text(raw.get("start_time")), text(raw.get("end_time"))
        if any(item and not valid_time(item) for item in (start, end)):
            raise AgentError("שעות הסבב חייבות להיות בפורמט HH:MM")
        result.append({
            "days": text_list(raw.get("days") or []),
            "shifts": text_list(raw.get("shifts") or []),
            "start_time": start,
            "end_time": end,
            "reason": text(raw.get("reason")),
        })
    return result


def rules(rows: Any) -> List[dict]:
    if not isinstance(rows, list):
        raise AgentError("רשימת הכללים אינה תקינה")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not text(row.get("text")):
            raise AgentError("לכל כלל חייב להיות ניסוח")
        priority = text(row.get("priority")) or "hard"
        if priority not in ("hard", "soft"):
            raise AgentError("עוצמת הכלל אינה תקינה")
        result.append({"text": text(row.get("text")), "priority": priority})
    return result


def audit_policy(value: dict) -> dict:
    result = dict(value)
    for field, label, minimum in _AUDIT_FIELDS:
        offered = result.get(field)
        if isinstance(offered, bool) or not isinstance(offered, (int, float)):
            raise AgentError("%s חייב להיות מספר" % label)
        if offered < minimum:
            raise AgentError("%s אינו יכול להיות קטן מ־%s" % (label, minimum))
    return result
