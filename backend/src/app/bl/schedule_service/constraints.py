"""Constraints the manager records, and the change history they join."""

import datetime
from typing import Any, List, Optional

from app.bl.schedule_service.constants import ACTION_CONSTRAINT
from app.bl.schedule_service.rows import text
from app.common.errors.errors import AgentError
from app.dal.repository.schedules import SOURCE_MANAGER


class ConstraintService:
    def __init__(self, repository):
        self._repository = repository

    def set_constraint(
        self,
        team_id: str,
        employee: str,
        constraint_date: str,
        shift_name: str = "",
        available: bool = False,
        start_time: str = "",
        end_time: str = "",
        is_hard: bool = True,
        reason: str = "",
        source: str = SOURCE_MANAGER,
    ) -> dict:
        """Record a constraint for an employee.

        Written by the manager or by the agent during a conversation, so
        `source` records where the information came from rather than who
        typed it. `employee_reported` is the manager writing down what
        someone told them (D10/D13).
        """
        employee = (employee or "").strip()
        if not employee:
            raise AgentError("צריך לציין עובד")
        if not (constraint_date or "").strip():
            raise AgentError("צריך לציין תאריך")
        shift_name = (shift_name or "").strip()
        reason = (reason or "").strip()
        row = self._repository.set_availability(
            team_id, employee, constraint_date,
            shift_name=shift_name,
            available=available,
            start_time=_constraint_time(start_time),
            end_time=_constraint_time(end_time),
            is_hard=is_hard, reason=reason, source=source,
        )
        self._repository.append_change(
            team_id, ACTION_CONSTRAINT,
            employee=employee, slot_date=constraint_date,
            shift_name=shift_name, reason=reason,
            agent_reason=_constraint_note(available, is_hard),
        )
        return row

    def constraints(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        employee: Optional[str] = None,
    ) -> List[dict]:
        return self._repository.availability(
            team_id, starts_on, ends_on, employee
        )

    def delete_constraint(self, row_id: str, team_id: str) -> None:
        self._repository.delete_availability(row_id, team_id)

    def history(
        self, team_id: str, schedule_id: Optional[str] = None
    ) -> List[dict]:
        return self._repository.change_log(team_id, schedule_id)


def _constraint_note(available: bool, is_hard: bool) -> str:
    if not is_hard:
        return "העדפת זמינות נרשמה"
    return "זמין" if available else "אילוץ נרשם"


def _constraint_time(value: Any) -> str:
    """Validate an optional wall-clock bound at the service boundary."""
    stated = text(value)
    if not stated:
        return ""
    try:
        parsed = datetime.time.fromisoformat(stated)
    except ValueError:
        raise AgentError("שעת האילוץ אינה תקינה")
    return parsed.strftime("%H:%M")
