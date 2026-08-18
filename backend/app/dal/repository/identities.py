"""Employee identity and the one thing an employee may write.

Both halves of [D14](../../../docs/DECISIONS.md#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10),
which reversed D5 and amended D10 deliberately. Before it, a member was a
holder of a shared link and nothing more -- indistinguishable from every other
member, which is why "his hours" could not be expressed at all.

Two things live here and nothing else:

- **`employee_identities`** -- a claim over a NAME from the workplace profile,
  protected by a personal passcode. Not a user record: `employee` matches
  `assignments.employee` exactly, because the whole product identifies people
  by the name the interview recorded and a second identifier would have to be
  reconciled with the first on every read.
- **`constraint_requests`** -- a submission awaiting the manager. Deliberately
  NOT a row in `availability`: a pending request must be invisible to
  `audit.py`, so that asking cannot move the arithmetic
  ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
  Approval is what promotes it, and approval is a manager action.

Passcodes reuse `teams.hash_password` rather than a second scheme. One
password format in the codebase means one place to change when scrypt's cost
parameters are next revisited, and the properties an employee passcode needs
are exactly the properties the boss password already has.
"""

import datetime
from typing import List, Optional

from app.common.errors import AgentError, AuthError, ConflictError
from app.dal.repository.base import RepositoryBase, new_id
from app.dal.repository.teams import hash_password, verify_password

# Request lifecycle. `withdrawn` is the employee taking it back before anyone
# ruled on it -- distinct from `rejected` because "I changed my mind" and "the
# manager said no" are different facts, and collapsing them would lose the
# only one of the two the employee controls.
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_WITHDRAWN = "withdrawn"
_DECIDED = (STATUS_APPROVED, STATUS_REJECTED)

# A passcode short enough to be forgettable is worse than none, since it
# invites reuse of something guessable across a small team where everyone
# knows everyone.
_MIN_PASSCODE = 4


class IdentityRepository(RepositoryBase):

    # -- identities --------------------------------------------------------

    def claim_identity(
        self, team_id: str, employee: str, passcode: str
    ) -> dict:
        """Claim a name in this team. Refuses a name already claimed.

        The refusal is the point: without the unique constraint two people
        could hold the same name and each would see the other's hours. A
        `ConflictError` rather than an upsert -- silently rebinding a claimed
        name to whoever asked last is an account takeover with the share link
        as its only requirement.
        """
        employee = (employee or "").strip()
        if not employee:
            raise AgentError("יש לבחור שם עובד")
        if len(passcode or "") < _MIN_PASSCODE:
            raise AgentError("קוד אישי חייב להכיל לפחות 4 תווים")
        if self.find_identity(team_id, employee) is not None:
            raise ConflictError("השם הזה כבר משויך. פנו למנהל אם זו טעות")
        self._execute("""
            INSERT INTO employee_identities
                (id, team_id, employee, passcode_hash)
            VALUES (%s,%s,%s,%s)
        """, (new_id(), team_id, employee, hash_password(passcode)))
        return self._one("""
            SELECT id, team_id, employee, created_at, last_seen_at
            FROM employee_identities WHERE team_id=%s AND employee=%s
        """, (team_id, employee))

    def authenticate_employee(
        self, team_id: str, employee: str, passcode: str
    ) -> dict:
        """The identity if the passcode matches, `AuthError` otherwise.

        Mirrors `authenticate_boss`: one message for both "no such claim" and
        "wrong passcode", and the hash is verified against a dummy when the
        row is missing so a nonexistent claim takes the same time as a wrong
        code. Otherwise this endpoint reports which names are claimed, to
        anyone holding the share link.
        """
        rows = self._all("""
            SELECT * FROM employee_identities WHERE team_id=%s AND employee=%s
        """, (team_id, (employee or "").strip()))
        row = rows[0] if rows else None
        stored = row["passcode_hash"] if row else hash_password("")
        if not verify_password(passcode or "", stored) or row is None:
            raise AuthError("השם או הקוד האישי שגויים")
        self._execute(
            "UPDATE employee_identities SET last_seen_at=NOW() WHERE id=%s",
            (row["id"],),
        )
        return row

    def find_identity(self, team_id: str, employee: str) -> Optional[dict]:
        rows = self._all("""
            SELECT id, team_id, employee, created_at, last_seen_at,
                   acknowledged_at
            FROM employee_identities WHERE team_id=%s AND employee=%s
        """, (team_id, (employee or "").strip()))
        return rows[0] if rows else None

    def acknowledge(self, team_id: str, employee: str) -> None:
        """Mark everything up to now as seen by this employee.

        Separate from `last_seen_at`, which moves on every login: by the time
        the personal area renders, that one is already "now" and nothing
        could ever be new against it. This advances only when the employee
        says they have read what they were shown, which is what makes "what
        changed for me since I last looked" answerable (D16).
        """
        self._execute("""
            UPDATE employee_identities SET acknowledged_at=NOW()
            WHERE team_id=%s AND employee=%s
        """, (team_id, (employee or "").strip()))

    def claimed_names(self, team_id: str) -> List[str]:
        """Which names are already taken.

        Feeds the claim screen so it can grey out taken names instead of
        letting someone pick one and fail. Names only -- never the hashes.
        """
        rows = self._all("""
            SELECT employee FROM employee_identities WHERE team_id=%s
            ORDER BY employee
        """, (team_id,))
        return [row["employee"] for row in rows]

    def list_identities(self, team_id: str) -> List[dict]:
        """Every claim in the team, for the manager's roster panel."""
        return self._all("""
            SELECT id, employee, created_at, last_seen_at
            FROM employee_identities WHERE team_id=%s
            ORDER BY employee
        """, (team_id,))

    def release_identity(self, team_id: str, employee: str) -> None:
        """Drop a claim so the name can be claimed again.

        The manager's tool for someone who left or who lost their passcode.
        Rotating the share link does not do this -- the link and the claim are
        separate credentials, which is exactly why a departure needs both.

        Their submitted requests are deliberately left standing: those are
        history, and an approved one has already become an `availability` row
        that the schedule may depend on.
        """
        self._execute("""
            DELETE FROM employee_identities WHERE team_id=%s AND employee=%s
        """, (team_id, (employee or "").strip()))

    # -- constraint requests -----------------------------------------------

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
        if status not in _DECIDED:
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


__all__ = [
    "IdentityRepository",
    "STATUS_PENDING", "STATUS_APPROVED", "STATUS_REJECTED", "STATUS_WITHDRAWN",
]
