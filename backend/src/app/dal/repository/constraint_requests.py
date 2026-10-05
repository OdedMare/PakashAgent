"""An employee's constraint submission awaiting the manager (D14).

Deliberately NOT a row in `availability`: a pending request must be
invisible to `audit.py`, so that asking cannot move the arithmetic (D3)."""

from typing import List, Optional

from app.common.errors.errors import AgentError, AuthError, ConflictError
from app.dal.repository.base import RepositoryBase, new_id
from app.dal.repository.request_status import (
    DECIDED, STATUS_PENDING, STATUS_WITHDRAWN,
)


class ConstraintRequestRepository(RepositoryBase):
    def submit_request(
        self,
        team_id: str,
        employee: str,
        constraint_date: str,
        shift_name: str = "",
        available: bool = False,
        reason: str = "",
    ) -> dict:
        """Record a submission. Changes nothing about the schedule.

        `employee` is taken from the caller's session, never from the request
        body -- an employee submitting under someone else's name is the one
        abuse this surface makes possible, and the fix is not to accept the
        name at all.

        A second pending request for the same date and shift replaces the
        first rather than queueing beside it: a person restating a constraint
        means the same one, and two rows would give the manager two identical
        decisions to make.
        """
        employee = (employee or "").strip()
        if not employee:
            raise AgentError("חסר שם עובד")
        if not constraint_date:
            raise AgentError("חסר תאריך")
        self._execute("""
            UPDATE constraint_requests SET status=%s
            WHERE team_id=%s AND employee=%s AND constraint_date=%s
              AND shift_name=%s AND status=%s
        """, (STATUS_WITHDRAWN, team_id, employee, constraint_date,
              shift_name or "", STATUS_PENDING))
        row_id = new_id()
        self._execute("""
            INSERT INTO constraint_requests (
                id, team_id, employee, constraint_date, shift_name,
                available, reason, status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (row_id, team_id, employee, constraint_date, shift_name or "",
              bool(available), reason or "", STATUS_PENDING))
        return self.get_request(row_id, team_id)

    def get_request(self, request_id: str, team_id: str) -> dict:
        return self._one("""
            SELECT * FROM constraint_requests WHERE id=%s AND team_id=%s
        """, (request_id, team_id))

    def list_requests(
        self,
        team_id: str,
        employee: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[dict]:
        """Requests, newest first.

        The manager reads this unfiltered by employee; an employee reads it
        with their own name bound from their session, which is what keeps one
        person's stated reasons ("medical appointment") from being readable by
        the rest of the team.
        """
        query = "SELECT * FROM constraint_requests WHERE team_id=%s"
        params: List[object] = [team_id]
        if employee:
            query += " AND employee=%s"
            params.append(employee)
        if status:
            query += " AND status=%s"
            params.append(status)
        query += " ORDER BY created_at DESC"
        return self._all(query, tuple(params))

    def decide_request(
        self,
        request_id: str,
        team_id: str,
        status: str,
        decided_reason: str = "",
    ) -> dict:
        """Mark a request approved or rejected. Writes no constraint itself.

        Promoting an approval into an `availability` row is `bl/`'s job, not
        this module's: it spans two tables and is a decision about what an
        approval *means*, which is business logic. Here it is only the ruling.

        Only a pending request can be decided. Deciding one twice would let a
        rejection quietly become an approval later with nothing recording that
        it changed.
        """
        if status not in DECIDED:
            raise AgentError("החלטה לא תקינה")
        current = self.get_request(request_id, team_id)
        if current["status"] != STATUS_PENDING:
            raise ConflictError("הבקשה כבר טופלה")
        self._execute("""
            UPDATE constraint_requests
            SET status=%s, decided_reason=%s, decided_at=NOW()
            WHERE id=%s AND team_id=%s
        """, (status, decided_reason or "", request_id, team_id))
        return self.get_request(request_id, team_id)

    def withdraw_request(
        self, request_id: str, team_id: str, employee: str
    ) -> dict:
        """The employee taking back their own pending request.

        Scoped by employee as well as team: the id alone must not let one
        person withdraw another's request.
        """
        current = self.get_request(request_id, team_id)
        if current["employee"] != (employee or "").strip():
            raise AuthError("אין הרשאה לבקשה הזו")
        if current["status"] != STATUS_PENDING:
            raise ConflictError("הבקשה כבר טופלה")
        self._execute("""
            UPDATE constraint_requests SET status=%s WHERE id=%s AND team_id=%s
        """, (STATUS_WITHDRAWN, request_id, team_id))
        return self.get_request(request_id, team_id)

    def pending_count(self, team_id: str) -> int:
        """How many requests are waiting, for the manager's badge."""
        rows = self._all("""
            SELECT count(*) AS n FROM constraint_requests
            WHERE team_id=%s AND status=%s
        """, (team_id, STATUS_PENDING))
        return int(rows[0]["n"]) if rows else 0
