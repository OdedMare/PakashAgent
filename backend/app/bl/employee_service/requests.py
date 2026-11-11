"""Constraint requests: an employee submits, the manager rules.

**Approval is the only thing that writes a constraint.** A pending request is
inert: invisible to the audit, absent from the schedule, and incapable of
moving a number (D3).
"""

from typing import List

from app.bl.employee_service.values import (
    ACTION_REQUEST_REJECTED, iso_date, require_reason,
)
from app.dal.repository.identities import (
    STATUS_APPROVED, STATUS_PENDING, STATUS_REJECTED,
)
from app.dal.repository.schedules import SOURCE_EMPLOYEE_REPORTED


class ConstraintRequests:
    def __init__(self, repository, schedules):
        self._repository = repository
        self._schedules = schedules

    def submit(
        self, team_id: str, employee: str, constraint_date: str,
        shift_name: str = "", available: bool = False, reason: str = "",
    ) -> dict:
        """Submit a constraint request. Writes no constraint."""
        return self._repository.submit_request(
            team_id, employee, constraint_date,
            shift_name=(shift_name or "").strip(),
            available=available, reason=(reason or "").strip(),
        )

    def withdraw(self, team_id: str, employee: str, request_id: str) -> dict:
        return self._repository.withdraw_request(request_id, team_id, employee)

    def my_requests(self, team_id: str, employee: str) -> List[dict]:
        return self._repository.list_requests(team_id, employee=employee)

    def pending(self, team_id: str) -> List[dict]:
        """Requests awaiting a decision, for the manager's inbox."""
        return self._repository.list_requests(team_id, status=STATUS_PENDING)

    def all_requests(self, team_id: str) -> List[dict]:
        return self._repository.list_requests(team_id)

    def approve(self, team_id: str, request_id: str, decided_reason: str = "") -> dict:
        """Approve a request and promote it into a real constraint.

        The ruling, then the `availability` row it creates, with
        `source='employee_reported'` -- the D13 value for "this came from the
        employee". This is the moment the request becomes countable.
        """
        request = self._repository.decide_request(
            request_id, team_id, STATUS_APPROVED, decided_reason
        )
        constraint = self._schedules.set_constraint(
            team_id,
            request["employee"],
            iso_date(request["constraint_date"]),
            shift_name=request.get("shift_name") or "",
            available=bool(request.get("available")),
            reason=request.get("reason") or "",
            source=SOURCE_EMPLOYEE_REPORTED,
        )
        return {"request": request, "constraint": constraint}

    def reject(self, team_id: str, request_id: str, decided_reason: str = "") -> dict:
        """Reject a request, with a reason the employee will read.

        Required: a rejection that says nothing is how a submission channel
        stops being used (the D8 argument).
        """
        reason = require_reason(decided_reason, "צריך לציין סיבה לדחייה")
        request = self._repository.decide_request(
            request_id, team_id, STATUS_REJECTED, reason
        )
        self._repository.append_change(
            team_id, ACTION_REQUEST_REJECTED,
            employee=request["employee"],
            slot_date=iso_date(request["constraint_date"]),
            shift_name=request.get("shift_name") or "",
            reason=reason,
            agent_reason="בקשת אילוץ נדחתה",
        )
        return {"request": request}
