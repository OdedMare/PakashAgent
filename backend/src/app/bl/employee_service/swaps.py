"""Shift swaps: two employees agree, the manager rules, the agent's path applies.

Accepting is consent, not approval: it moves the swap into the manager's inbox
and no further. D14 gave employees exactly one write, widened from "a
constraint request" to "a request", with the manager as sole decider.
"""

from typing import List

from app.bl.employee_service.values import (
    ACTION_SWAP_REJECTED, find_assignment, iso_date, require_reason, text,
)
from app.common.errors import AgentError, AuthError
from app.dal.repository.identities import (
    STATUS_APPROVED, STATUS_AWAITING, STATUS_PENDING, STATUS_REJECTED,
)


class SwapRequests:
    def __init__(self, repository, schedules):
        self._repository = repository
        self._schedules = schedules

    def propose_swap(
        self, team_id: str, employee: str, assignment_id: str,
        counterparty: str, counterparty_assignment_id: str, reason: str = "",
    ) -> dict:
        """Offer a swap to a colleague. Moves nothing.

        Both shifts are named by *assignment id*, so a swap can never name a
        shift that is not really on the schedule, and both are verified to
        belong to the people they are claimed for. Read from the published
        schedule only -- a draft shift is not the manager's commitment yet.
        """
        schedule = self._schedules.current(team_id, role="member")
        if not schedule:
            raise AgentError("אין סידור מפורסם להחליף בו משמרות")
        mine = find_assignment(schedule, assignment_id)
        theirs = find_assignment(schedule, counterparty_assignment_id)
        if mine is None or theirs is None:
            raise AgentError("אחת המשמרות לא נמצאה בסידור")
        if text(mine.get("employee")) != employee:
            raise AuthError("אפשר להציע רק משמרת שלך")
        if text(theirs.get("employee")) != (counterparty or "").strip():
            raise AgentError("המשמרת שנבחרה אינה של העובד שנבחר")
        return self._repository.submit_swap(
            team_id, schedule["id"], employee,
            iso_date(mine.get("date")), text(mine.get("shift")),
            text(theirs.get("employee")),
            iso_date(theirs.get("date")), text(theirs.get("shift")),
            reason=(reason or "").strip(),
        )

    def answer_swap(self, team_id: str, employee: str, swap_id: str, agreed: bool) -> dict:
        """The colleague accepting or declining. Still moves nothing."""
        return self._repository.answer_swap(swap_id, team_id, employee, agreed)

    def withdraw_swap(self, team_id: str, employee: str, swap_id: str) -> dict:
        return self._repository.withdraw_swap(swap_id, team_id, employee)

    def my_swaps(self, team_id: str, employee: str) -> List[dict]:
        """Every swap naming this person, on either side, labelled by side."""
        rows = self._repository.list_swaps(team_id, employee=employee)
        return [mark_side(row, employee) for row in rows]

    def incoming_swaps(self, team_id: str, employee: str) -> List[dict]:
        """Offers waiting on this employee's answer -- their badge."""
        return [
            mark_side(row, employee)
            for row in self._repository.list_swaps(
                team_id, employee=employee, status=STATUS_AWAITING
            )
            if text(row.get("counterparty")) == employee
        ]

    def pending_swaps(self, team_id: str) -> List[dict]:
        """Swaps both employees agreed to, awaiting the manager."""
        return self._repository.list_swaps(team_id, status=STATUS_PENDING)

    def all_swaps(self, team_id: str) -> List[dict]:
        return self._repository.list_swaps(team_id)

    def approve_swap(self, team_id: str, swap_id: str, decided_reason: str = "") -> dict:
        """Approve a swap and perform it through `schedule_service.apply`.

        The *same* `OP_SWAP` path a manager-typed swap takes, so the history
        reads as one kind of event. The manager's reason is required (D8);
        `agent_reason` states the provenance rather than inventing a judgment.
        """
        reason = require_reason(decided_reason, "צריך לציין סיבה לאישור ההחלפה")
        swap = self._repository.decide_swap(swap_id, team_id, STATUS_APPROVED, reason)
        schedule = self._schedules.apply(
            team_id, swap["schedule_id"], [_swap_operation(swap)], reason,
            agent_reason=swap_note(swap),
        )
        return {"swap": swap, "schedule": schedule}

    def reject_swap(self, team_id: str, swap_id: str, decided_reason: str = "") -> dict:
        """Refuse a swap, with a reason both employees will read."""
        reason = require_reason(decided_reason, "צריך לציין סיבה לדחייה")
        swap = self._repository.decide_swap(swap_id, team_id, STATUS_REJECTED, reason)
        self._repository.append_change(
            team_id, ACTION_SWAP_REJECTED,
            schedule_id=swap.get("schedule_id"),
            employee=swap["requester"],
            replaced_employee=swap["counterparty"],
            slot_date=iso_date(swap["requester_date"]),
            shift_name=swap.get("requester_shift") or "",
            reason=reason,
            agent_reason="בקשת החלפה נדחתה",
        )
        return {"swap": swap}


def _swap_operation(swap: dict) -> dict:
    return {
        "action": "swap",
        "employee": swap["requester"],
        "shift": swap.get("requester_shift") or "",
        "date": iso_date(swap["requester_date"]),
        "with_employee": swap["counterparty"],
        "with_shift": swap.get("counterparty_shift") or "",
        "with_date": iso_date(swap["counterparty_date"]),
    }


def mark_side(row: dict, employee: str) -> dict:
    """Label which side of the swap the reader is on."""
    return dict(
        row,
        is_requester=text(row.get("requester")) == employee,
        is_counterparty=text(row.get("counterparty")) == employee,
    )


def swap_note(swap: dict) -> str:
    """What the change log records as the agent's half of the reason (D18)."""
    note = "החלפה שסוכמה בין {} ל{} ואושרה על ידי המנהל".format(
        swap.get("requester") or "", swap.get("counterparty") or ""
    )
    reason = (swap.get("reason") or "").strip()
    return "{}. הסיבה שנמסרה: {}".format(note, reason) if reason else note
