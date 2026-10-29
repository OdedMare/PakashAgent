"""Validating the roster: service types, exit patterns, rotation groups."""

import datetime
import re
from typing import Any, List

from app.bl.profile_service.validation import named_rows, text, text_list, valid_time
from app.bl.rotation.vocabulary import groups_for
from app.bl.shared import HEBREW_WEEKDAYS, weekday_key
from app.common.errors import AgentError

_SERVICE_TYPES = ("standard", "overlap", "reserve")
_EXIT_PATTERNS = ("round", "triplet", "quad", "hamshushim", "shushim")
_GROUPED = ("round", "triplet", "quad")
# A day cycle is named by its id; whether that id exists is checked against
# the workplace in `validate_rotation_groups`, once both halves are merged.
_DAY_CYCLE = re.compile(r"^cycle:[A-Za-z0-9_-]{1,32}$")


def employees(rows: Any, default_exit_pattern: str = "round") -> List[dict]:
    return [_employee(row, default_exit_pattern) for row in named_rows(rows, "עובד")]


def _employee(row: dict, default_exit_pattern: str) -> dict:
    if row.get("inactive_from"):
        try:
            row["inactive_from"] = datetime.date.fromisoformat(row["inactive_from"]).isoformat()
        except (ValueError, TypeError):
            raise AgentError("תאריך סיום העבודה חייב להיות בפורמט YYYY-MM-DD")
    service_type = text(row.get("service_type")) or "standard"
    if service_type not in _SERVICE_TYPES:
        raise AgentError("סוג כוח האדם אינו תקין")
    exit_pattern = text(row.get("exit_pattern")) or default_exit_pattern
    if exit_pattern not in _EXIT_PATTERNS and not _DAY_CYCLE.match(exit_pattern):
        raise AgentError("מבנה היציאות של איש הצוות אינו תקין")
    recurring = row.get("recurring_constraints") or []
    if not isinstance(recurring, list):
        raise AgentError("האילוצים הקבועים של איש הצוות אינם תקינים")
    _validate_recurring(recurring)
    row.update({
        "service_type": service_type,
        "exit_pattern": exit_pattern,
        # Kept for every pattern, because a group is what makes one rotate:
        # a חמשושים person *with* a group goes out on their group's weekends.
        "rotation_group": text(row.get("rotation_group")),
        "role": text(row.get("role")),
        "notes": text(row.get("notes")),
        "is_shift_manager": bool(row.get("is_shift_manager")),
        "can_train": bool(row.get("can_train")),
        "eligible_shifts": text_list(row.get("eligible_shifts") or []),
        "is_trainee": service_type == "overlap",
        "is_casual": service_type == "reserve",
        "recurring_constraints": recurring,
    })
    if not isinstance(row.get("counts_toward_staffing"), bool):
        row["counts_toward_staffing"] = service_type != "overlap"
    return row


def _validate_recurring(rows: list) -> None:
    weekdays = {weekday_key(day) for day in HEBREW_WEEKDAYS}
    fields = {"days", "shifts", "available", "is_hard", "start_time", "end_time", "reason", "source", "constraint_type"}
    for rule in rows:
        if isinstance(rule, str):
            # Older free-text profile prose is preserved; only structured rules expand.
            continue
        if not isinstance(rule, dict) or set(rule) - fields \
                or not isinstance(rule.get("days"), list) \
                or not isinstance(rule.get("shifts"), list) \
                or not isinstance(rule.get("available"), bool):
            raise AgentError("אילוץ קבוע חייב להכיל days ו-shifts כרשימות ו-available כערך בוליאני; אין להשתמש ב-day_of_week או shift")
        if any(weekday_key(day) not in weekdays for day in rule["days"]) \
                or any(not isinstance(shift, str) or not shift.strip() for shift in rule["shifts"]):
            raise AgentError("ימי האילוץ חייבים להיות שמות ימים בעברית, והמשמרות חייבות להיות רשימת שמות")
        if "is_hard" in rule and not isinstance(rule["is_hard"], bool):
            raise AgentError("is_hard באילוץ קבוע חייב להיות ערך בוליאני")
        if any(rule.get(key) and (not isinstance(rule[key], str) or not valid_time(rule[key]))
               for key in ("start_time", "end_time")):
            raise AgentError("שעות האילוץ הקבוע חייבות להיות בפורמט HH:MM")
        constraint_type = rule.get("constraint_type") or "availability"
        if constraint_type not in ("availability", "duty"):
            raise AgentError("סוג האילוץ הקבוע אינו תקין")
        if constraint_type == "duty" and (
            rule["available"] or rule.get("is_hard", True) is False
            or rule["shifts"] or not rule.get("start_time") or not rule.get("end_time")
        ):
            raise AgentError("תורנות קבועה חייבת להיות קשיחה, עם שעת התחלה וסיום וללא משמרת מסוימת")


def employee_item(item: dict) -> dict:
    """An agent-proposed roster row, in the shape the editor writes."""
    return {
        "name": item.get("name"),
        "role": item.get("role") or "",
        "eligible_shifts": item.get("eligible_shifts") or [],
        "exit_pattern": item.get("exit_pattern") or "round",
        "rotation_group": item.get("rotation_group") or "",
        "is_shift_manager": bool(item.get("is_shift_manager")),
        "can_train": bool(item.get("can_train")),
        "notes": item.get("notes") or "",
    }


def validate_rotation_groups(profile: dict) -> None:
    """Every stated group belongs to the cycle its owner turns on.

    חמשושים and שושים say how long a closure runs, not how many groups take
    turns, so their group is checked against the unit's own cycle.
    """
    workplace = profile.get("workplace") or {}
    mode = text(workplace.get("rotation_mode")) or "round"
    cycles = {
        "cycle:%s" % text(row.get("id")): row for row in workplace.get("day_cycles") or []
        if isinstance(row, dict)
    }
    for person in profile.get("employees") or []:
        pattern = text(person.get("exit_pattern")) or mode
        if pattern.startswith("cycle:"):
            _check_day_cycle(person, cycles.get(pattern))
            continue
        cycle = pattern if pattern in _GROUPED else mode
        groups = set(groups_for(cycle) or groups_for("round"))
        group = text(person.get("rotation_group"))
        if group and group not in groups:
            raise AgentError("קבוצת הסבב של %s אינה מתאימה למבנה היחידה" % (
                text(person.get("name")) or "איש הצוות"
            ))


def _check_day_cycle(person: dict, cycle) -> None:
    name = text(person.get("name")) or "איש הצוות"
    if cycle is None:
        raise AgentError("מחזור היציאות של %s אינו מוגדר ביחידה" % name)
    if text(person.get("rotation_group")) not in (cycle.get("groups") or []):
        raise AgentError("יש לבחור ל%s קבוצה מתוך %s" % (name, text(cycle.get("name")) or "המחזור"))


def validate_first_profile(profile: dict) -> None:
    if not text((profile.get("workplace") or {}).get("name")):
        raise AgentError("יש להזין שם יחידה")
    if not profile.get("employees"):
        raise AgentError("יש להוסיף לפחות איש צוות אחד")
    if any(
        person.get("exit_pattern") in _GROUPED and not text(person.get("rotation_group"))
        for person in profile.get("employees") or []
    ):
        raise AgentError("יש לבחור קבוצת סבב, תלתון או רבעון לכל איש צוות מתאים")
    if not profile.get("shifts"):
        raise AgentError("יש להוסיף לפחות סוג משמרת אחד")
