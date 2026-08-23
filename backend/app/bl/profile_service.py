"""Manual editing of the workplace roster and shift vocabulary."""

import copy
from typing import Any, List, Optional

from app.common.errors import AgentError, NotFoundError


class ProfileService:
    """Keep profile edits on the interview profile, with small validation."""

    def __init__(self, repository):
        self._repository = repository

    def update(
        self,
        team_id: str,
        employees: Optional[List[dict]] = None,
        shifts: Optional[List[dict]] = None,
    ) -> dict:
        profile = self._repository.team_profile(team_id)
        if profile is None:
            raise NotFoundError("פרופיל הצוות לא נמצא")
        updated = copy.deepcopy(profile)
        if employees is not None:
            edited = _employees(employees)
            _keep_existing_names(profile.get("employees"), edited, "עובד")
            updated["employees"] = edited
        if shifts is not None:
            edited = _shifts(shifts)
            _keep_existing_names(profile.get("shifts"), edited, "משמרת")
            updated["shifts"] = edited
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
    }


def _shift_item(item: dict) -> dict:
    return {
        "name": item.get("name"),
        "start_time": item.get("start_time") or "",
        "end_time": item.get("end_time") or "",
        "headcount": item.get("headcount") or 1,
        "is_on_call": bool(item.get("is_on_call")),
    }


def _employees(rows: Any) -> List[dict]:
    return _named_rows(rows, "עובד")


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
        row["is_on_call"] = bool(row.get("is_on_call", False))
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
