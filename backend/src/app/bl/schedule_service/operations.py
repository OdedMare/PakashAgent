"""Confirmed change operations, applied to the store or imagined in memory.

`OperationApplier` writes one confirmed operation and logs it; `preview`
computes the assignment list a proposal *would* leave, without writing, so the
audit can report on a change the manager has not accepted yet. Both read the
same three actions, so each action is one small handler rather than a branch
in a long method.
"""

from typing import Callable, Dict, List, Optional

from app.bl.changes import OP_ASSIGN, OP_REMOVE, OP_SWAP
from app.bl.schedule_service.constants import (
    ACTION_ASSIGNED,
    ACTION_REMOVED,
    ACTION_SWAPPED,
)
from app.bl.schedule_service.rows import assignment_facts, iso


class Operation:
    """One proposed operation, read once with its fields normalised."""

    def __init__(self, raw: dict, agent_reason: str = ""):
        raw = raw or {}
        self.action = raw.get("action")
        self.employee = (raw.get("employee") or "").strip()
        self.shift = (raw.get("shift") or "").strip()
        self.date = iso(raw.get("date"))
        self.other = (raw.get("with_employee") or "").strip()
        self.other_shift = (raw.get("with_shift") or "").strip() or self.shift
        self.other_date = iso(raw.get("with_date")) or self.date
        self.own_reason = (raw.get("reason") or "").strip() or agent_reason

    @property
    def is_complete(self) -> bool:
        return bool(self.action and self.employee and self.date)


def match(schedule: dict, employee: str, shift: str, date: str) -> Optional[dict]:
    """The stored assignment an operation names, if it is there.

    An empty `shift` means the whole day -- "take Dana off Thursday" names a
    person and a date, and `changes.py` relies on this reading.
    """
    for row in schedule.get("assignments") or []:
        if (
            row.get("employee") == employee
            and iso(row.get("date")) == date
            and (not shift or row.get("shift") == shift)
        ):
            return row
    return None


class OperationApplier:
    def __init__(self, repository):
        self._repository = repository
        self._handlers: Dict[str, Callable] = {
            OP_REMOVE: self._remove,
            OP_ASSIGN: self._assign,
            OP_SWAP: self._swap,
        }

    def apply(
        self,
        team_id: str,
        schedule: dict,
        raw: dict,
        reason: str,
        agent_reason: str,
    ) -> int:
        """One operation against the stored schedule. Returns rows changed."""
        operation = Operation(raw, agent_reason)
        handler = self._handlers.get(operation.action)
        if handler is None or not operation.is_complete:
            return 0
        return handler(team_id, schedule, operation, reason)

    def _remove(
        self, team_id: str, schedule: dict, op: Operation, reason: str
    ) -> int:
        existing = match(schedule, op.employee, op.shift, op.date)
        if existing is None:
            return 0
        self._repository.remove_assignment(existing["id"], team_id)
        self._log(team_id, schedule, op, reason, ACTION_REMOVED)
        return 1

    def _assign(
        self, team_id: str, schedule: dict, op: Operation, reason: str
    ) -> int:
        slot = self._repository.find_slot(
            schedule["id"], team_id, op.shift, op.date
        )
        if slot is None:
            return 0
        self._repository.add_assignment(
            schedule["id"], team_id, slot["id"], op.employee,
            op.own_reason or reason,
        )
        self._log(team_id, schedule, op, reason, ACTION_ASSIGNED)
        return 1

    def _swap(
        self, team_id: str, schedule: dict, op: Operation, reason: str
    ) -> int:
        first = match(schedule, op.employee, op.shift, op.date)
        second = match(schedule, op.other, op.other_shift, op.other_date)
        if first is None or second is None:
            return 0
        stored_reason = op.own_reason or reason
        self._repository.move_assignment(
            first["id"], team_id, second["slot_id"], reason=stored_reason,
        )
        self._repository.move_assignment(
            second["id"], team_id, first["slot_id"], reason=stored_reason,
        )
        self._log(
            team_id, schedule, op, reason, ACTION_SWAPPED,
            replaced_employee=op.other,
        )
        return 1

    def _log(
        self,
        team_id: str,
        schedule: dict,
        op: Operation,
        reason: str,
        action: str,
        **extra
    ) -> None:
        self._repository.append_change(
            team_id, action, schedule_id=schedule["id"],
            employee=op.employee, slot_date=op.date, shift_name=op.shift,
            reason=reason, agent_reason=op.own_reason, **extra
        )


def preview(schedule: dict, operations: List[dict]) -> List[dict]:
    """The assignment list as a proposal would leave it. Never written."""
    rows = assignment_facts(schedule.get("assignments"))
    for raw in operations or []:
        action = raw.get("action")
        employee, shift = raw.get("employee"), raw.get("shift")
        date = iso(raw.get("date"))
        if action == OP_REMOVE:
            rows = [
                row for row in rows
                if not (row["employee"] == employee and row["date"] == date
                        and (not shift or row["shift"] == shift))
            ]
        elif action == OP_ASSIGN:
            rows.append({"employee": employee, "shift": shift, "date": date})
        elif action == OP_SWAP:
            _swap_in_memory(rows, raw, employee, shift, date)
    return rows


def _swap_in_memory(
    rows: List[dict], raw: dict, employee: str, shift: str, date: str
) -> None:
    other = raw.get("with_employee")
    other_shift = raw.get("with_shift") or shift
    other_date = iso(raw.get("with_date")) or date
    for row in rows:
        if (row["employee"] == employee and row["date"] == date
                and row["shift"] == shift):
            row["employee"] = other
        elif (row["employee"] == other and row["date"] == other_date
                and row["shift"] == other_shift):
            row["employee"] = employee


def nothing_applied(operations: List[dict]) -> str:
    """Why a confirmed proposal changed nothing, as the manager reads it.

    One operation named, not all of them: a manager handed a list of four
    targets that were not found reads none of them, and the first is what the
    request was mostly about.
    """
    first = next((row for row in operations if isinstance(row, dict)), None)
    if first is None:
        return "לא היה שינוי להחיל"
    employee = (first.get("employee") or "").strip()
    shift = (first.get("shift") or "").strip()
    date = iso(first.get("date"))
    if first.get("action") == OP_ASSIGN:
        return (
            "לא ניתן לשבץ את %s: אין משמרת %s בתאריך %s בסידור הזה."
            % (employee, shift or "המבוקשת", date)
        )
    return (
        "לא נמצא שיבוץ של %s ל%s בתאריך %s, אז לא בוצע שינוי."
        % (employee, shift or "אותו יום", date)
    )


def moved_from(previous: Optional[dict]) -> str:
    """A default agent reason for a drag the manager did not annotate.

    Says what happened rather than pretending to a judgment the agent did not
    make — the manager moved this, and the log should read that way.
    """
    if not previous:
        return "הועבר על ידי המנהל"
    return "הועבר על ידי המנהל מ%s ב-%s" % (
        previous.get("shift") or "", iso(previous.get("date")),
    )
