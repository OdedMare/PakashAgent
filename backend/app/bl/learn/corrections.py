"""What the manager kept overriding, counted from the change log. No model.

Uploaded files say what the workplace *did*; the change log says what the
manager **corrected**, and D8 guarantees every correction carries a reason. A
correction is a decision, so it is stronger evidence than a counted absence --
but still only a candidate until the manager says so.
"""

from typing import Any, Dict, List

from app.bl.hebrew_calendar import hebrew_weekday
from app.bl.learn.values import bounded, bounded_rows, date_of, iso_or_blank, text

# Two is deliberately low: the second time a manager makes the same
# correction is exactly when they would say "yes, that is a rule". One is not
# a pattern; it is a Tuesday.
_MIN_CORRECTIONS = 2

# The actions that override a placement. `assigned` is deliberately absent:
# filling an empty cell takes nothing from anybody (D18) and corrects nothing.
_CORRECTING_ACTIONS = ("moved", "removed", "swapped")
_MAX_REASON_CHARS = 200


class _Tally:
    """One (person, shift, weekday) pattern of corrections.

    Keyed on what a rule would be about -- Fridays, not the 3rd of March.
    Reasons are collected verbatim, never summarised or merged: deciding two
    sentences mean the same is a language job for the model.
    """

    def __init__(self, employee: str, shift: str, weekday: str, date):
        self.employee, self.shift, self.weekday = employee, shift, weekday
        self.count = 0
        self.reasons: List[str] = []
        self.first_seen = self.last_seen = date

    def add(self, row: dict, date) -> None:
        self.count += 1
        reason = bounded(row.get("reason"), _MAX_REASON_CHARS)
        if reason and reason not in self.reasons:
            self.reasons.append(reason)
        if date is not None:
            self.first_seen = date if self.first_seen is None else min(self.first_seen, date)
            self.last_seen = date if self.last_seen is None else max(self.last_seen, date)

    def to_dict(self) -> dict:
        return {
            "employee": self.employee,
            "shift": self.shift,
            "weekday": self.weekday,
            "count": self.count,
            "reasons": self.reasons,
            "first_seen": iso_or_blank(self.first_seen),
            "last_seen": iso_or_blank(self.last_seen),
        }


def observe_corrections(changes: List[dict]) -> dict:
    """Repeated corrections, most-corrected first, with the manager's reasons.

    "You moved Yossi off Friday evening three times, saying 'לימודים' twice"
    is a claim the manager can confirm or dismiss at a glance.
    """
    rows = bounded_rows(changes)
    tallies: Dict[tuple, _Tally] = {}
    by_employee: Dict[str, int] = {}
    for row in rows:
        employee = _subject(row)
        if not employee:
            continue
        by_employee[employee] = by_employee.get(employee, 0) + 1
        date = date_of(row.get("slot_date"))
        key = (employee, text(row.get("shift_name")), hebrew_weekday(date))
        tallies.setdefault(key, _Tally(*key, date)).add(row, date)
    repeated = [t.to_dict() for t in tallies.values() if t.count >= _MIN_CORRECTIONS]
    repeated.sort(key=lambda item: (-item["count"], item["employee"]))
    return {
        "repeated": repeated,
        "totals": {
            "changes": len(rows),
            "corrections": sum(by_employee.values()),
            "people": len(by_employee),
        },
        # Below the floor nothing is claimed, but the count is still reported
        # so the model can say "not enough yet" rather than invent a reason.
        "single_corrections": sum(1 for t in tallies.values() if t.count < _MIN_CORRECTIONS),
    }


def _subject(row: Any) -> str:
    """Who a correcting row is about, or empty when it is not a correction.

    On a move or a swap the person taken *off* the shift is the subject;
    `replaced_employee` carries them where the log recorded one.
    """
    if text(row.get("action")) not in _CORRECTING_ACTIONS:
        return ""
    return text(row.get("replaced_employee")) or text(row.get("employee"))
