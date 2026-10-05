"""Two employees agreeing to trade shifts, then the manager ruling on it."""

from typing import List, Optional

from app.common.errors.errors import AgentError, AuthError, ConflictError
from app.dal.repository.base import RepositoryBase, new_id
from app.dal.repository.request_status import (
    DECIDED, STATUS_AWAITING, STATUS_DECLINED, STATUS_PENDING, STATUS_WITHDRAWN,
)


class SwapRepository(RepositoryBase):
    def submit_swap(
        self,
        team_id: str,
        schedule_id: str,
        requester: str,
        requester_date: str,
        requester_shift: str,
        counterparty: str,
        counterparty_date: str,
        counterparty_shift: str,
        reason: str = "",
    ) -> dict:
        """Record a proposed swap. Moves no assignment.

        `requester` comes from the caller's session exactly as it does on a
        constraint submission, and for the same reason: proposing a swap in
        someone else's name is the abuse this surface makes possible.

        The counterparty is checked against the roster rather than trusted:
        an unclaimed or misspelled name would produce a swap nobody can
        answer, which sits in the requester's list forever looking pending.

        Unlike a constraint, a repeat is *refused* rather than superseded. A
        constraint restated means the same fact; a second swap offer to the
        same person for the same shift is either a duplicate click or an
        attempt to nag, and neither should displace an offer the other side
        may already be looking at.
        """
        requester, counterparty = _parties(
            requester, counterparty, requester_date, counterparty_date
        )
        if self._open_swap_exists(
            team_id, requester, counterparty, requester_date, requester_shift
        ):
            raise ConflictError("כבר קיימת בקשת החלפה פתוחה על המשמרת הזו")
        row_id = new_id()
        self._execute("""
            INSERT INTO swap_requests (
                id, team_id, schedule_id, requester, requester_date,
                requester_shift, counterparty, counterparty_date,
                counterparty_shift, reason, status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (row_id, team_id, schedule_id, requester, requester_date,
              requester_shift or "", counterparty, counterparty_date,
              counterparty_shift or "", reason or "", STATUS_AWAITING))
        return self.get_swap(row_id, team_id)

    def _open_swap_exists(
        self, team_id: str, requester: str, counterparty: str,
        requester_date: str, requester_shift: str,
    ) -> bool:
        return bool(self._all("""
            SELECT id FROM swap_requests
            WHERE team_id=%s AND requester=%s AND counterparty=%s
              AND requester_date=%s AND requester_shift=%s
              AND status IN (%s,%s)
        """, (team_id, requester, counterparty, requester_date,
              requester_shift or "", STATUS_AWAITING, STATUS_PENDING)))

    def get_swap(self, swap_id: str, team_id: str) -> dict:
        return self._one("""
            SELECT * FROM swap_requests WHERE id=%s AND team_id=%s
        """, (swap_id, team_id))

    def list_swaps(
        self,
        team_id: str,
        employee: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[dict]:
        """Swaps, newest first.

        `employee` matches **either** side. A swap is one row that two people
        both need to see, so an employee's list is everything naming them --
        filtering on `requester` alone would hide from the counterparty the
        very request they are being asked to answer.
        """
        query = "SELECT * FROM swap_requests WHERE team_id=%s"
        params: List[object] = [team_id]
        if employee:
            query += " AND (requester=%s OR counterparty=%s)"
            params.extend([employee, employee])
        if status:
            query += " AND status=%s"
            params.append(status)
        query += " ORDER BY created_at DESC"
        return self._all(query, tuple(params))

    def answer_swap(
        self, swap_id: str, team_id: str, employee: str, agreed: bool
    ) -> dict:
        """The counterparty accepting or declining.

        Scoped to the counterparty specifically -- not to either side. The
        requester answering their own proposal would be consent from the one
        person whose consent the row already records.

        Acceptance moves the swap to `pending`, which is the first moment it
        appears in the manager's inbox. A decline ends it: the requester can
        propose another, to the same person or a different one.
        """
        current = self.get_swap(swap_id, team_id)
        if current["counterparty"] != (employee or "").strip():
            raise AuthError("אין הרשאה לבקשה הזו")
        if current["status"] != STATUS_AWAITING:
            raise ConflictError("הבקשה כבר טופלה")
        self._execute("""
            UPDATE swap_requests
            SET status=%s, counterparty_agreed=%s, counterparty_replied_at=NOW()
            WHERE id=%s AND team_id=%s
        """, (STATUS_PENDING if agreed else STATUS_DECLINED, bool(agreed),
              swap_id, team_id))
        return self.get_swap(swap_id, team_id)

    def decide_swap(
        self,
        swap_id: str,
        team_id: str,
        status: str,
        decided_reason: str = "",
    ) -> dict:
        """The manager's ruling. Moves no assignment itself.

        Performing the swap is `bl/`'s job for the reason `decide_request`
        gives: it spans tables and is a decision about what an approval
        *means*. Here it is only the ruling.

        Only a `pending` swap can be decided, which is what stops a manager
        from approving an arrangement the counterparty has not accepted --
        the guard is the status, not the UI that usually hides it.
        """
        if status not in DECIDED:
            raise AgentError("החלטה לא תקינה")
        current = self.get_swap(swap_id, team_id)
        if current["status"] != STATUS_PENDING:
            raise ConflictError("הבקשה אינה ממתינה להחלטת מנהל")
        self._execute("""
            UPDATE swap_requests
            SET status=%s, decided_reason=%s, decided_at=NOW()
            WHERE id=%s AND team_id=%s
        """, (status, decided_reason or "", swap_id, team_id))
        return self.get_swap(swap_id, team_id)

    def withdraw_swap(
        self, swap_id: str, team_id: str, employee: str
    ) -> dict:
        """The requester taking back their own proposal.

        Allowed while the counterparty is still deciding *and* after they
        agreed but before the manager ruled: the shift is still the
        requester's until it is actually swapped, and a person whose plans
        changed should not have to ask the manager to undo a swap that never
        happened.
        """
        current = self.get_swap(swap_id, team_id)
        if current["requester"] != (employee or "").strip():
            raise AuthError("אין הרשאה לבקשה הזו")
        if current["status"] not in (STATUS_AWAITING, STATUS_PENDING):
            raise ConflictError("הבקשה כבר טופלה")
        self._execute("""
            UPDATE swap_requests SET status=%s WHERE id=%s AND team_id=%s
        """, (STATUS_WITHDRAWN, swap_id, team_id))
        return self.get_swap(swap_id, team_id)

    def pending_swap_count(self, team_id: str) -> int:
        """Swaps waiting on the manager, for the inbox badge.

        Counts `pending` only. One still awaiting its counterparty is not
        the manager's to act on and would inflate a badge that is supposed
        to mean "there is something for you to do".
        """
        rows = self._all("""
            SELECT count(*) AS n FROM swap_requests
            WHERE team_id=%s AND status=%s
        """, (team_id, STATUS_PENDING))
        return int(rows[0]["n"]) if rows else 0


def _parties(requester, counterparty, requester_date, counterparty_date) -> tuple:
    """Both names trimmed, after checking a swap between them is possible."""
    requester = (requester or "").strip()
    counterparty = (counterparty or "").strip()
    if not requester or not counterparty:
        raise AgentError("חסר שם עובד")
    if requester == counterparty:
        raise AgentError("אי אפשר להחליף משמרת עם עצמך")
    if not requester_date or not counterparty_date:
        raise AgentError("חסר תאריך")
    return requester, counterparty
