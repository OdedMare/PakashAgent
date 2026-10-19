"""A claim over a roster name, protected by a personal passcode (D14)."""

from typing import List, Optional

from app.common.errors import AgentError, AuthError, ConflictError
from app.dal.repository.base import RepositoryBase, new_id
from app.dal.repository.request_status import (
    MIN_PASSCODE,
)
from app.dal.repository.teams import hash_password, verify_password


class EmployeeIdentityRepository(RepositoryBase):
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
        if len(passcode or "") < MIN_PASSCODE:
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
