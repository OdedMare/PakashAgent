"""Operations folded into an in-memory copy of a period. Nothing to save.

Works on audit rows rather than stored assignments because that is what
`audit()` reads and what nothing can accidentally save: there are no row ids
here to hand a repository.
"""

from typing import Any, Callable, Dict, List, Optional

from app.bl.changes import OP_ASSIGN, OP_REMOVE, OP_SWAP

# The same bound a proposal has: a simulation is a proposal not yet asked
# for, and letting it be larger would make "simulate" the way to describe a
# change too big to propose.
MAX_OPERATIONS = 40


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return text(value)


def schedule_rows(schedule: dict) -> List[dict]:
    return [
        {
            "employee": text(row.get("employee")),
            "shift": text(row.get("shift")),
            "date": iso(row.get("date")),
        }
        for row in (schedule or {}).get("assignments") or [] if isinstance(row, dict)
    ]


def find(rows: List[dict], employee: str, shift: str, date: str) -> Optional[dict]:
    """One person's row on one slot. An empty `shift` matches any shift that
    day -- "take דנה off Thursday" is the ordinary case."""
    for row in rows:
        if text(row.get("employee")) == employee and iso(row.get("date")) == date \
                and (not shift or text(row.get("shift")) == shift):
            return row
    return None


class Hypothetical:
    """A period's rows with operations applied, plus what was and was not."""

    def __init__(self, rows: List[dict], schedule: dict):
        self.rows = [dict(row) for row in rows]
        self.applied: List[dict] = []
        self.skipped: List[dict] = []
        self._slots = {
            (text(slot.get("shift_name")), iso(slot.get("slot_date")))
            for slot in (schedule or {}).get("slots") or []
        }
        self._handlers: Dict[str, Callable[[dict, str, str, str], Optional[str]]] = {
            OP_REMOVE: self._remove, OP_ASSIGN: self._assign, OP_SWAP: self._swap,
        }

    def apply_all(self, operations: Any) -> "Hypothetical":
        for item in (operations if isinstance(operations, list) else [])[:MAX_OPERATIONS]:
            if isinstance(item, dict):
                self._apply(item)
        return self

    def _apply(self, item: dict) -> None:
        action, employee = text(item.get("action")), text(item.get("employee"))
        shift, date = text(item.get("shift")), iso(item.get("date"))
        handler = self._handlers.get(action)
        if handler is None or not employee or not date:
            self.skipped.append(dict(item, why="הפעולה אינה שלמה"))
            return
        why = handler(item, employee, shift, date)
        if why:
            self.skipped.append(dict(item, why=why))
        else:
            self.applied.append(dict(item, action=action))

    def _remove(self, item: dict, employee: str, shift: str, date: str) -> Optional[str]:
        match = find(self.rows, employee, shift, date)
        if match is None:
            return "%s לא משובץ/ת שם" % employee
        self.rows.remove(match)
        return None

    def _assign(self, item: dict, employee: str, shift: str, date: str) -> Optional[str]:
        if self._slots and (shift, date) not in self._slots:
            return "אין משמרת כזו בתקופה"
        self.rows.append({"employee": employee, "shift": shift, "date": date})
        return None

    def _swap(self, item: dict, employee: str, shift: str, date: str) -> Optional[str]:
        """Two people trade the slots they are each already on."""
        other_shift = text(item.get("with_shift")) or shift
        other_date = iso(item.get("with_date")) or date
        first = find(self.rows, employee, shift, date)
        second = find(self.rows, text(item.get("with_employee")), other_shift, other_date)
        if first is None or second is None:
            return "אחד מהשניים לא משובץ שם"
        first["shift"], first["date"] = other_shift, other_date
        second["shift"], second["date"] = shift, date
        return None
