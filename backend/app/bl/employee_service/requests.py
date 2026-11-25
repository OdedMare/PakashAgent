"""Constraint requests: an employee submits, the manager rules.

**Approval is the only thing that writes a constraint.** A pending request is
inert: invisible to the audit, absent from the schedule, and incapable of
moving a number (D3).
"""

from datetime import date, timedelta
from typing import List

from app.common.errors import AppError

from app.bl.change_plans.confirmed import apply_confirmed_change
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
        end_date: str = "", before_shift: str = "", after_shift: str = "",
    ) -> dict:
        """Submit a constraint request. Writes no constraint."""
        try:
            first = date.fromisoformat(constraint_date)
            last = date.fromisoformat(end_date or constraint_date)
        except ValueError:
            raise AppError("תאריך לא תקין")
        if last < first:
            raise AppError("תאריך הסיום קודם לתאריך ההתחלה")
        if (last - first).days >= 366:
            raise AppError("אפשר להגיש עד 366 ימים בבקשה אחת")
        if available and (before_shift or after_shift):
            raise AppError("חסימת משמרות סמוכות אפשרית רק בבקשת אי־זמינות")
        if (before_shift and first == date.min) or (after_shift and last == date.max):
            raise AppError("תאריך המשמרת הסמוכה מחוץ לטווח")
        return self._repository.submit_request(
            team_id, employee, first.isoformat(),
            end_date=last.isoformat(), before_shift=before_shift.strip(), after_shift=after_shift.strip(),
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
        return apply_confirmed_change(
            self._repository,
            team_id,
            source="employee_request",
            body={
                "kind": "constraint_request", "request_id": request_id,
                "decision": "approved", "reason": decided_reason,
            },
            apply=lambda: self._approve(team_id, request_id, decided_reason),
            message="בקשת האילוץ אושרה ונשמרה",
            reason=decided_reason,
            agent_reason="בקשת אילוץ של עובד אושרה על ידי המנהל",
        )

    def _approve(self, team_id, request_id, decided_reason):
        request = self._repository.decide_request(
            request_id, team_id, STATUS_APPROVED, decided_reason
        )
        first = date.fromisoformat(iso_date(request["constraint_date"]))
        last = date.fromisoformat(iso_date(request.get("end_date") or first))
        slots = [(first + timedelta(days=i), request.get("shift_name") or "")
                 for i in range((last - first).days + 1)]
        if request.get("before_shift"):
            slots.append((first - timedelta(days=1), request["before_shift"]))
        if request.get("after_shift"):
            slots.append((last + timedelta(days=1), request["after_shift"]))
        constraints = [
            self._schedules.set_constraint(
                team_id, request["employee"], day.isoformat(), shift_name=shift,
                available=bool(request.get("available")), reason=request.get("reason") or "",
                source=SOURCE_EMPLOYEE_REPORTED,
            )
            for day, shift in slots
        ]
        return {"request": request, "constraint": constraints[0], "constraints": constraints}

    def reject(self, team_id: str, request_id: str, decided_reason: str = "") -> dict:
        """Reject a request, with a reason the employee will read.

        Required: a rejection that says nothing is how a submission channel
        stops being used (the D8 argument).
        """
        reason = require_reason(decided_reason, "צריך לציין סיבה לדחייה")
        return apply_confirmed_change(
            self._repository,
            team_id,
            source="employee_request",
            body={
                "kind": "constraint_request", "request_id": request_id,
                "decision": "rejected", "reason": reason,
            },
            apply=lambda: self._reject(team_id, request_id, reason),
            message="בקשת האילוץ נדחתה",
            reason=reason,
            agent_reason="בקשת אילוץ נדחתה על ידי המנהל",
        )

    def _reject(self, team_id, request_id, reason):
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
