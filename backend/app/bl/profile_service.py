"""Manual editing of the complete workplace profile."""

import copy
import datetime
from typing import Any, List, Optional

from app.common.errors import AgentError, NotFoundError


_TEXT_SECTIONS = (
    "availability_process", "constraint_deadline", "casual_worker_policy",
    "rest_policy", "weekend_policy", "fairness_policy", "conflict_policy",
    "existing_schedule_source", "summary",
)
_OBJECT_SECTIONS = ("training_policy", "audit_policy")
_OPTIONAL_EXIT_PATTERNS = ("triplet", "hamshushim", "shushim")


class ProfileService:
    """Keep profile edits on the interview profile, with small validation."""

    def __init__(self, repository):
        self._repository = repository

    def update(
        self,
        team_id: str,
        employees: Optional[List[dict]] = None,
        shifts: Optional[List[dict]] = None,
        workplace: Optional[dict] = None,
        rules: Optional[List[dict]] = None,
        dependencies: Optional[List[str]] = None,
        **sections: Any
    ) -> dict:
        profile = self._repository.team_profile(team_id)
        creating = profile is None
        current = profile or {}
        updated = copy.deepcopy(current)
        if workplace is not None:
            offered_workplace = dict(current.get("workplace") or {})
            offered_workplace.update(workplace)
            updated["workplace"] = _workplace(offered_workplace)
        if employees is not None:
            workplace_for_defaults = updated.get("workplace") or {}
            edited = _employees(
                employees,
                default_exit_pattern=_text(
                    workplace_for_defaults.get("rotation_mode")
                ) or "round",
            )
            _keep_existing_names(current.get("employees"), edited, "עובד")
            updated["employees"] = edited
        if shifts is not None:
            edited = _shifts(shifts)
            _keep_existing_names(current.get("shifts"), edited, "משמרת")
            updated["shifts"] = edited
        if rules is not None:
            updated["rules"] = _rules(rules)
        if dependencies is not None:
            updated["dependencies"] = _text_list(dependencies)
        for key in _OBJECT_SECTIONS:
            if key in sections and sections[key] is not None:
                if not isinstance(sections[key], dict):
                    raise AgentError("פרטי המדיניות אינם תקינים")
                updated[key] = (
                    _audit_policy(sections[key])
                    if key == "audit_policy" else dict(sections[key])
                )
        for key in _TEXT_SECTIONS:
            if key in sections and sections[key] is not None:
                updated[key] = _text(sections[key])

        _validate_rotation_groups(updated)
        if creating:
            _validate_first_profile(updated)
            updated["completeness"] = {
                "complete": True, "missing_topics": [], "open_points": [],
            }
            return self._repository.create_team_profile(team_id, updated)
        return self._repository.update_team_profile(team_id, updated)

    def apply_operations(self, team_id: str, operations: List[dict]) -> dict:
        """Apply confirmed agent operations through the same validation path."""
        profile = self._repository.team_profile(team_id)
        if profile is None:
            raise NotFoundError("פרופיל הצוות לא נמצא")
        employees = [dict(row) for row in profile.get("employees") or []]
        shifts = [dict(row) for row in profile.get("shifts") or []]
        employees_changed = False
        shifts_changed = False

        for operation in operations or []:
            action = _text((operation or {}).get("action"))
            target = _text((operation or {}).get("target"))
            item = (operation or {}).get("item")
            item = dict(item) if isinstance(item, dict) else {}
            if action == "add_employee":
                employees.append(_employee_item(item))
                employees_changed = True
            elif action == "update_employee":
                item["name"] = target
                employees = _replace(
                    employees, target, _employee_item(item), "עובד"
                )
                employees_changed = True
            elif action == "add_shift":
                shifts.append(_shift_item(item))
                shifts_changed = True
            elif action == "update_shift":
                item["name"] = target
                shifts = _replace(
                    shifts, target, _shift_item(item), "משמרת"
                )
                shifts_changed = True
            else:
                raise AgentError("פעולת פרופיל אינה נתמכת")

        return self.update(
            team_id,
            employees=employees if employees_changed else None,
            shifts=shifts if shifts_changed else None,
        )


def _replace(rows: List[dict], target: str, item: dict, label: str) -> List[dict]:
    if not target:
        raise AgentError("חסר שם ה%s לעריכה" % label)
    found = False
    result = []
    for row in rows:
        if _text(row.get("name")) == target:
            result.append(dict(row, **item))
            found = True
        else:
            result.append(row)
    if not found:
        raise AgentError("ה%s לא נמצא בפרופיל" % label)
    return result


def _employee_item(item: dict) -> dict:
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


def _shift_item(item: dict) -> dict:
    return {
        "name": item.get("name"),
        "start_time": item.get("start_time") or "",
        "end_time": item.get("end_time") or "",
        "headcount": item.get("headcount") or 1,
        "is_on_call": bool(item.get("is_on_call")),
        "requires_shift_manager": bool(item.get("requires_shift_manager")),
    }


def _employees(rows: Any, default_exit_pattern: str = "round") -> List[dict]:
    result = _named_rows(rows, "עובד")
    for row in result:
        service_type = _text(row.get("service_type")) or "standard"
        if service_type not in ("standard", "overlap", "reserve"):
            raise AgentError("סוג כוח האדם אינו תקין")
        row["service_type"] = service_type
        exit_pattern = _text(row.get("exit_pattern")) or default_exit_pattern
        if exit_pattern not in ("round", "triplet", "hamshushim", "shushim"):
            raise AgentError("מבנה היציאות של איש הצוות אינו תקין")
        row["exit_pattern"] = exit_pattern
        row["rotation_group"] = (
            _text(row.get("rotation_group"))
            if exit_pattern in ("round", "triplet") else ""
        )
        row["role"] = _text(row.get("role"))
        row["notes"] = _text(row.get("notes"))
        row["is_shift_manager"] = bool(row.get("is_shift_manager"))
        row["can_train"] = bool(row.get("can_train"))
        row["eligible_shifts"] = _text_list(row.get("eligible_shifts") or [])
        row["is_trainee"] = service_type == "overlap"
        row["is_casual"] = service_type == "reserve"
        if not isinstance(row.get("counts_toward_staffing"), bool):
            row["counts_toward_staffing"] = service_type != "overlap"
        recurring = row.get("recurring_constraints") or []
        if not isinstance(recurring, list):
            raise AgentError("האילוצים הקבועים של איש הצוות אינם תקינים")
        row["recurring_constraints"] = recurring
    return result


def _shifts(rows: Any) -> List[dict]:
    result = _named_rows(rows, "משמרת")
    for row in result:
        for field in ("start_time", "end_time"):
            value = _text(row.get(field))
            if value and not _valid_time(value):
                raise AgentError("שעת המשמרת חייבת להיות בפורמט HH:MM")
            row[field] = value
        default_staffing = next((
            group for group in row.get("staffing") or []
            if isinstance(group, dict)
            and (not isinstance(group.get("days"), list) or not group["days"])
        ), {})
        try:
            headcount = max(1, int(
                row.pop("headcount", None)
                or default_staffing.get("headcount")
                or 1
            ))
        except (TypeError, ValueError):
            raise AgentError("מספר העובדים במשמרת חייב להיות מספר")
        staffing = [
            dict(group) for group in row.get("staffing") or []
            if isinstance(group, dict) and group.get("days")
        ]
        row["staffing"] = [
            {
                "days": [],
                "headcount": headcount,
                "required_roles": default_staffing.get("required_roles") or [],
            }
        ] + staffing
        shift_type = _text(row.get("shift_type")) or (
            "on_call" if row.get("is_on_call") else "regular"
        )
        if shift_type not in ("regular", "overlap", "on_call"):
            raise AgentError("סוג המשמרת אינו תקין")
        row["shift_type"] = shift_type
        row["purpose"] = _text(row.get("purpose"))
        row["is_on_call"] = shift_type == "on_call"
        row["requires_shift_manager"] = bool(
            row.get("requires_shift_manager")
        )
    return result


def _workplace(value: Any) -> dict:
    if not isinstance(value, dict):
        raise AgentError("פרטי היחידה אינם תקינים")
    result = dict(value)
    result["name"] = _text(result.get("name"))
    result["planning_horizon"] = _text(
        result.get("planning_horizon")
    ) or "שבוע"
    result["operating_days"] = _text_list(result.get("operating_days") or [])
    mode = _text(result.get("rotation_mode")) or "round"
    if mode not in ("round", "triplet"):
        raise AgentError("מבנה הסבב אינו תקין")
    groups = ["א", "ב"] if mode == "round" else ["א", "ב", "ג"]
    first_group = _text(result.get("first_closure_group")) or groups[0]
    if first_group not in groups:
        raise AgentError("קבוצת הסגירה הראשונה אינה מתאימה למבנה הסבב")
    first_date = _text(result.get("first_closure_date"))
    if first_date:
        try:
            datetime.date.fromisoformat(first_date)
        except ValueError:
            raise AgentError("תאריך הסגירה הראשונה אינו תקין")
    result["rotation_mode"] = mode
    result["first_closure_group"] = first_group
    result["first_closure_date"] = first_date
    result["general_exit_schedule"] = _text(
        result.get("general_exit_schedule")
    )
    enabled_patterns = _text_list(
        result.get("enabled_exit_patterns") or []
    )
    if any(pattern not in _OPTIONAL_EXIT_PATTERNS
           for pattern in enabled_patterns):
        raise AgentError("מבנה היציאות האופציונלי אינו תקין")
    result["enabled_exit_patterns"] = list(dict.fromkeys(enabled_patterns))
    result["rotation_a_unavailability"] = _rotation_rules(
        result.get("rotation_a_unavailability") or []
    )
    return result


def _rotation_rules(value: Any) -> List[dict]:
    """Rotation A uses the same shape as recurring employee constraints."""
    if not isinstance(value, list):
        raise AgentError("זמני אי־הזמינות של סבב א׳ אינם תקינים")
    result = []
    for raw in value:
        if not isinstance(raw, dict):
            raise AgentError("פרטי אי־הזמינות של סבב א׳ אינם תקינים")
        start_time = _text(raw.get("start_time"))
        end_time = _text(raw.get("end_time"))
        if any(value and not _valid_time(value)
               for value in (start_time, end_time)):
            raise AgentError("שעות הסבב חייבות להיות בפורמט HH:MM")
        result.append({
            "days": _text_list(raw.get("days") or []),
            "shifts": _text_list(raw.get("shifts") or []),
            "start_time": start_time,
            "end_time": end_time,
            "reason": _text(raw.get("reason")),
        })
    return result


def _rules(rows: Any) -> List[dict]:
    if not isinstance(rows, list):
        raise AgentError("רשימת הכללים אינה תקינה")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not _text(row.get("text")):
            raise AgentError("לכל כלל חייב להיות ניסוח")
        priority = _text(row.get("priority")) or "hard"
        if priority not in ("hard", "soft"):
            raise AgentError("עוצמת הכלל אינה תקינה")
        result.append({"text": _text(row.get("text")), "priority": priority})
    return result


def _text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        raise AgentError("הרשימה אינה תקינה")
    return [item for item in (_text(raw) for raw in value) if item]


def _validate_first_profile(profile: dict) -> None:
    workplace = profile.get("workplace") or {}
    if not _text(workplace.get("name")):
        raise AgentError("יש להזין שם יחידה")
    if not profile.get("employees"):
        raise AgentError("יש להוסיף לפחות איש צוות אחד")
    if any(
        person.get("exit_pattern") in ("round", "triplet")
        and not _text(person.get("rotation_group"))
        for person in profile.get("employees") or []
    ):
        raise AgentError("יש לבחור קבוצת סבב או תלתון לכל איש צוות מתאים")
    if not profile.get("shifts"):
        raise AgentError("יש להוסיף לפחות סוג משמרת אחד")


def _validate_rotation_groups(profile: dict) -> None:
    for person in profile.get("employees") or []:
        pattern = _text(person.get("exit_pattern")) or _text(
            (profile.get("workplace") or {}).get("rotation_mode")
        ) or "round"
        groups = {"א", "ב", "ג"} if pattern == "triplet" else {"א", "ב"}
        group = _text(person.get("rotation_group"))
        if pattern in ("round", "triplet") and group and group not in groups:
            raise AgentError("קבוצת הסבב של %s אינה מתאימה למבנה היחידה" % (
                _text(person.get("name")) or "איש הצוות"
            ))


def _audit_policy(value: dict) -> dict:
    result = dict(value)
    for field, label, minimum in (
        ("max_weekly_hours", "מקסימום שעות בשבוע", 0),
        ("max_consecutive_days", "מקסימום ימים רצופים", 1),
        ("min_rest_hours", "מינימום מנוחה בין משמרות", 0),
    ):
        offered = result.get(field)
        if isinstance(offered, bool) or not isinstance(offered, (int, float)):
            raise AgentError("%s חייב להיות מספר" % label)
        if offered < minimum:
            raise AgentError("%s אינו יכול להיות קטן מ־%s" % (label, minimum))
    return result


def _named_rows(rows: Any, label: str) -> List[dict]:
    if not isinstance(rows, list):
        raise AgentError("הרשימה אינה תקינה")
    result = []
    seen = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise AgentError("פרטי ה%s אינם תקינים" % label)
        row = dict(raw)
        name = _text(row.get("name"))
        if not name:
            raise AgentError("לכל %s חייב להיות שם" % label)
        if name in seen:
            raise AgentError("השם %s מופיע יותר מפעם אחת" % name)
        seen.add(name)
        row["name"] = name
        result.append(row)
    return result


def _keep_existing_names(before: Any, after: List[dict], label: str) -> None:
    """Names are identity keys; renaming/removal needs an explicit migration."""
    old = {
        _text(row.get("name")) for row in before or []
        if isinstance(row, dict) and _text(row.get("name"))
    }
    new = {_text(row.get("name")) for row in after}
    missing = sorted(old - new)
    if missing:
        raise AgentError(
            "לא ניתן לשנות או למחוק את שם ה%s %s; "
            "אפשר לערוך את שאר הפרטים או להוסיף שם חדש"
            % (label, missing[0])
        )


def _valid_time(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return False
    return 0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59


def _text(value: Any) -> str:
    return value.strip()[:200] if isinstance(value, str) else ""


__all__ = ["ProfileService"]
