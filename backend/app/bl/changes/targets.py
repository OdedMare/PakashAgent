"""Bounding proposed operations to targets the schedule actually has.

A dropped operation used to disappear: the model answered "העברתי את דנה
לערב", code found no slot for the row it named, and the manager got a
confident sentence with nothing to confirm. So what is dropped is returned
beside what is kept, and the proposal says which target was missing.

**An empty shift means "that day", not "no shift"** — the convention
`schedule_service.operations.match` has always used. One assignment that day
fills itself in, several is a question for the manager (D24), and none is a
target that is not there.
"""

from typing import Any, Dict, List, Optional

from app.bl.changes.schema import MAX_OPERATIONS, OP_REMOVE, OP_SWAP, OPERATIONS
from app.bl.changes.values import bounded, date_of

NOT_ASSIGNED = "not_assigned"
NO_SLOT = "no_slot"
AMBIGUOUS_SHIFT = "ambiguous_shift"


class ScheduleTargets:
    """The slots a period runs, and what each person is on per date."""

    def __init__(self, schedule: Optional[dict]):
        schedule = schedule or {}
        self.slots = {
            (bounded(slot.get("shift_name")), date_of(slot.get("slot_date")))
            for slot in schedule.get("slots") or []
        }
        # A removal is bounded by this rather than by the grid: a schedule with
        # no stored slots (an import, an older period) still has assignments.
        self.rostered: Dict[tuple, List[str]] = {}
        for row in schedule.get("assignments") or []:
            if not isinstance(row, dict):
                continue
            key = (bounded(row.get("employee")), date_of(row.get("date")))
            shift = bounded(row.get("shift"))
            if key[0] and key[1] and shift not in self.rostered.setdefault(key, []):
                self.rostered[key].append(shift)

    def resolve(
        self, action: str, employee: str, shift: str, date: str, fallback: str = "",
    ) -> tuple:
        """`(shift, why)`, `why` empty on success.

        A target the period does not have and a person not on that date are
        things to state; *several* possible shifts is the one case that is a
        question for the manager rather than a report (D24).
        """
        on_that_day = self.rostered.get((employee, date), [])
        if action == OP_REMOVE or (action == OP_SWAP and on_that_day):
            return self._existing_row(shift, date, on_that_day)
        shift = shift or fallback
        if shift:
            # An assignment needs a real slot to land on.
            return (shift, "") if (shift, date) in self.slots else ("", NO_SLOT)
        running = [name for name, day in self.slots if day == date]
        if len(running) == 1:
            # One shift runs that day, so naming it is not a guess.
            return running[0], ""
        return "", AMBIGUOUS_SHIFT if running else NO_SLOT

    def _existing_row(self, shift: str, date: str, on_that_day: List[str]) -> tuple:
        """Removing and swapping act on a row that exists: the roster answers.

        A named shift the period genuinely runs is a real target even when
        this person is not on it -- whether the row exists is something the
        manager can see, and the name gate may need to ask first.
        """
        if shift in on_that_day:
            return shift, ""
        if shift:
            if (shift, date) in self.slots:
                return shift, ""
            return "", NOT_ASSIGNED if on_that_day else NO_SLOT
        if len(on_that_day) == 1:
            return on_that_day[0], ""
        return "", AMBIGUOUS_SHIFT if on_that_day else NOT_ASSIGNED

    def options(self, action: str, employee: str, date: str) -> List[str]:
        """The shifts a held question can offer: one tap, not a sentence."""
        if action == OP_REMOVE:
            return sorted(self.rostered.get((employee, date), []))
        return sorted({name for name, day in self.slots if day == date})


def bound_operations(offered: Any, schedule: dict) -> tuple:
    """`(operations, dropped)` for what the model proposed.

    A shift and date the period does not contain is still dropped -- a check
    on whether the target exists, not on whether the choice was good.
    """
    if not isinstance(offered, list):
        return [], []
    targets = ScheduleTargets(schedule)
    operations, dropped = [], []
    for item in offered[:MAX_OPERATIONS]:
        if not isinstance(item, dict):
            continue
        operation = _bound_one(item, targets, dropped)
        if operation is not None:
            operations.append(operation)
    return operations, dropped


def _bound_one(item: dict, targets: ScheduleTargets, dropped: List[dict]):
    action, employee = bounded(item.get("action")), bounded(item.get("employee"))
    date = date_of(item.get("date"))
    if action not in OPERATIONS or not employee or not date:
        return None
    shift = _side(targets, action, employee, bounded(item.get("shift")), date, dropped)
    if shift is None:
        return None
    operation = {
        "action": action, "employee": employee, "shift": shift, "date": date,
        "reason": bounded(item.get("reason")),
    }
    if action != OP_SWAP:
        return operation
    other = bounded(item.get("with_employee"))
    if not other:
        return None
    other_date = date_of(item.get("with_date")) or date
    other_shift = _side(
        targets, action, other, bounded(item.get("with_shift")), other_date,
        dropped, fallback=shift,
    )
    if other_shift is None:
        return None
    operation.update({
        "with_employee": other, "with_shift": other_shift, "with_date": other_date,
    })
    return operation


def _side(
    targets: ScheduleTargets, action: str, employee: str, shift: str, date: str,
    dropped: List[dict], fallback: str = "",
) -> Optional[str]:
    """One side of an operation resolved, or None after recording the drop."""
    resolved, why = targets.resolve(action, employee, shift, date, fallback)
    if not why:
        return resolved
    dropped.append({
        "action": action, "employee": employee, "shift": shift, "date": date,
        "why": why, "options": targets.options(action, employee, date),
    })
    return None
