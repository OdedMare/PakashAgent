"""`ProfileService`: manual and agent-confirmed edits to the workplace profile."""

import copy
from typing import Any, Callable, Dict, List, Optional

from app.bl.profile_service import roster
from app.bl.profile_service import shifts as shift_rules
from app.bl.profile_service import workplace as workplace_rules
from app.bl.profile_service.validation import keep_existing_names, text, text_list
from app.common.errors.errors import AgentError, NotFoundError

_TEXT_SECTIONS = (
    "availability_process", "constraint_deadline", "casual_worker_policy",
    "rest_policy", "weekend_policy", "fairness_policy", "conflict_policy",
    "existing_schedule_source", "summary",
)
_OBJECT_SECTIONS = ("training_policy", "audit_policy")


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
        current = self._repository.team_profile(team_id)
        creating = current is None
        current = current or {}
        updated = _prepare_profile(current, employees, shifts, workplace, rules,
                                   dependencies, sections)
        if not creating:
            return self._repository.update_team_profile(team_id, updated)
        roster.validate_first_profile(updated)
        updated["completeness"] = {
            "complete": True, "missing_topics": [], "open_points": [],
        }
        return self._repository.create_team_profile(team_id, updated)

    def preview(self, team_id: str, **patch) -> dict:
        """Validate a conversational edit with the same rules, without writing."""
        current = self._repository.team_profile(team_id)
        if current is None:
            raise NotFoundError("פרופיל הצוות לא נמצא")
        return _prepare_profile(
            current, patch.get("employees"), patch.get("shifts"),
            patch.get("workplace"), patch.get("rules"), patch.get("dependencies"),
            patch,
        )

    def apply_operations(self, team_id: str, operations: List[dict]) -> dict:
        """Apply confirmed agent operations through the same validation path."""
        profile = self._repository.team_profile(team_id)
        if profile is None:
            raise NotFoundError("פרופיל הצוות לא נמצא")
        edit = _ProfileEdit(profile)
        for operation in operations or []:
            edit.apply(operation or {})
        return self.update(
            team_id,
            employees=edit.employees if edit.employees_changed else None,
            shifts=edit.shifts if edit.shifts_changed else None,
        )



def _prepare_profile(current, employees, shifts, workplace, rules, dependencies, sections):
    updated = copy.deepcopy(current)
    _apply_workplace(updated, current, workplace)
    _apply_roster(updated, current, employees, shifts)
    if rules is not None:
        updated["rules"] = workplace_rules.rules(rules)
    if dependencies is not None:
        updated["dependencies"] = text_list(dependencies)
    _apply_sections(updated, sections)
    roster.validate_rotation_groups(updated)
    return updated


def _apply_workplace(updated: dict, current: dict, offered: Optional[dict]) -> None:
    if offered is not None:
        merged = dict(current.get("workplace") or {})
        merged.update(offered)
        updated["workplace"] = workplace_rules.workplace(merged)


def _apply_roster(updated: dict, current: dict, employees, shift_rows) -> None:
    if employees is not None:
        default = text((updated.get("workplace") or {}).get("rotation_mode")) or "round"
        edited = roster.employees(employees, default_exit_pattern=default)
        keep_existing_names(current.get("employees"), edited, "עובד")
        updated["employees"] = edited
    if shift_rows is not None:
        edited = shift_rules.shifts(shift_rows)
        keep_existing_names(current.get("shifts"), edited, "משמרת")
        updated["shifts"] = edited


def _apply_sections(updated: dict, sections: Dict[str, Any]) -> None:
    for key in _OBJECT_SECTIONS:
        if sections.get(key) is None:
            continue
        if not isinstance(sections[key], dict):
            raise AgentError("פרטי המדיניות אינם תקינים")
        updated[key] = (
            workplace_rules.audit_policy(sections[key]) if key == "audit_policy"
            else dict(sections[key])
        )
    for key in _TEXT_SECTIONS:
        if sections.get(key) is not None:
            updated[key] = text(sections[key])


class _ProfileEdit:
    """The roster and vocabulary being edited by a list of agent operations."""

    def __init__(self, profile: dict):
        self.employees = [dict(row) for row in profile.get("employees") or []]
        self.shifts = [dict(row) for row in profile.get("shifts") or []]
        self.employees_changed = self.shifts_changed = False
        self._actions: Dict[str, Callable[[str, dict], None]] = {
            "add_employee": self._add_employee,
            "update_employee": self._update_employee,
            "add_shift": self._add_shift,
            "update_shift": self._update_shift,
        }

    def apply(self, operation: dict) -> None:
        action = self._actions.get(text(operation.get("action")))
        if action is None:
            raise AgentError("פעולת פרופיל אינה נתמכת")
        item = operation.get("item")
        action(text(operation.get("target")), dict(item) if isinstance(item, dict) else {})

    def _add_employee(self, target: str, item: dict) -> None:
        self.employees.append(roster.employee_item(item))
        self.employees_changed = True

    def _update_employee(self, target: str, item: dict) -> None:
        item["name"] = target
        self.employees = _replace(self.employees, target, roster.employee_item(item), "עובד")
        self.employees_changed = True

    def _add_shift(self, target: str, item: dict) -> None:
        self.shifts.append(shift_rules.shift_item(item))
        self.shifts_changed = True

    def _update_shift(self, target: str, item: dict) -> None:
        item["name"] = target
        self.shifts = _replace(self.shifts, target, shift_rules.shift_item(item), "משמרת")
        self.shifts_changed = True


def _replace(rows: List[dict], target: str, item: dict, label: str) -> List[dict]:
    if not target:
        raise AgentError("חסר שם ה%s לעריכה" % label)
    if not any(text(row.get("name")) == target for row in rows):
        raise AgentError("ה%s לא נמצא בפרופיל" % label)
    return [
        dict(row, **item) if text(row.get("name")) == target else row
        for row in rows
    ]
