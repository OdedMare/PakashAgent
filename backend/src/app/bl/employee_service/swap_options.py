"""Swaps one employee could offer that the audit finds clean. No LLM call.

What the employee assistant stands on (D27). The model phrases the answer;
this decides which swaps exist, so the assistant can never offer a trade the
audit would flag -- the same guarantee `find_replacements` gives the manager
(D19: never claim a placement is valid unless code said so).

**Colleagues' constraints are read here and never leave.** An option either
exists or is missing, with no reason attached. Why a teammate cannot take
Tuesday is the manager's to read, not a colleague's.

Only the *published* schedule is searched and only shifts from today on: a
draft is not the manager's commitment yet, and a past shift cannot be traded.
"""

import datetime
from typing import Dict, List, Tuple

from app.bl.audit import audit
from app.bl.changes import OP_SWAP
from app.bl.scheduler import effective_availability
from app.bl.shared.hebrew_calendar import hebrew_weekday
from app.bl.simulate.hypothetical import Hypothetical, schedule_rows
from app.bl.simulate.impact import warning_key
from app.bl.employee_service.values import employees, iso_date, shifts, text

# Options kept for each of the employee's shifts. Past a few the list stops
# being a suggestion and becomes a second grid to read.
_PER_SHIFT = 3
# Colleague shifts tried for each of the employee's shifts, nearest date
# first, and audits per question overall. Every check re-audits the period,
# so the bound is what keeps a question answering in well under a second.
_SCAN_PER_SHIFT = 30
_MAX_CHECKS = 300


def swap_options(
    schedule: dict, profile: dict, availability: List[dict],
    employee: str, today: datetime.date,
) -> List[dict]:
    """Clean swaps for `employee`, grouped by their own upcoming shift.

    An option is kept only when the swap introduces **no** warning anywhere
    in the period. One that clears a warning about the employee says so in
    `fixes` and is ranked first -- that is what "make my week work better"
    means in arithmetic.
    """
    name = text(employee)
    assignments = _upcoming(schedule, today)
    mine = [row for row in assignments if text(row.get("employee")) == name]
    others = [row for row in assignments if text(row.get("employee")) not in ("", name)]
    if not mine or not others:
        return []
    checker = _SwapChecker(schedule, profile, availability, name)
    options: List[dict] = []
    for own in mine:
        found = []
        for theirs in _nearest(own, others)[:_SCAN_PER_SHIFT]:
            if checker.spent():
                break
            fixes = checker.check(own, theirs)
            if fixes is not None:
                found.append((own, theirs, fixes))
        found.sort(key=lambda item: (-len(item[2]), _distance(own, item[1])))
        options.extend(_option(*item) for item in found[:_PER_SHIFT])
    for index, option in enumerate(options, start=1):
        option["id"] = "o%d" % index
    return options


class _SwapChecker:
    """The period audited once, then each candidate swap against it."""

    def __init__(self, schedule: dict, profile: dict, availability: List[dict], employee: str):
        self._schedule = schedule
        self._employee = employee
        self._shifts = shifts(profile)
        self._people = [row for row in employees(profile) if isinstance(row, dict)]
        self._profile = profile
        self._availability = effective_availability(
            profile, list(availability or []),
            iso_date(schedule.get("starts_on")), iso_date(schedule.get("ends_on")),
        )
        self._slots = [
            dict(slot, slot_date=iso_date(slot.get("slot_date")))
            for slot in schedule.get("slots") or [] if isinstance(slot, dict)
        ]
        self._rows = schedule_rows(schedule)
        self._before = self._keyed(self._rows)
        self._checks = 0

    def spent(self) -> bool:
        return self._checks >= _MAX_CHECKS

    def check(self, own: dict, theirs: dict):
        """The employee's warnings this swap clears, or None if it is not clean."""
        if _same_slot(own, theirs):
            return None
        self._checks += 1
        result = Hypothetical(self._rows, self._schedule).apply_all([_operation(own, theirs)])
        if result.skipped or not result.applied:
            return None
        after = self._keyed(result.rows)
        if any(key not in self._before for key in after):
            return None
        return [
            text(row.get("message"))
            for key, row in self._before.items()
            if key not in after and text(row.get("employee")) == self._employee
        ]

    def _keyed(self, rows: List[dict]) -> Dict[tuple, dict]:
        warnings = audit(rows, self._shifts, self._people, self._availability,
                         self._profile, self._slots)
        return {warning_key(row): row for row in warnings}


def _upcoming(schedule: dict, today: datetime.date) -> List[dict]:
    first = today.isoformat()
    return [
        row for row in (schedule or {}).get("assignments") or []
        if isinstance(row, dict) and text(row.get("id"))
        and iso_date(row.get("date")) >= first
    ]


def _nearest(own: dict, others: List[dict]) -> List[dict]:
    return sorted(others, key=lambda row: (_distance(own, row), iso_date(row.get("date"))))


def _distance(own: dict, theirs: dict) -> int:
    return abs((_day(own) - _day(theirs)).days)


def _day(row: dict) -> datetime.date:
    return datetime.date.fromisoformat(iso_date(row.get("date")))


def _same_slot(own: dict, theirs: dict) -> bool:
    return _slot(own) == _slot(theirs)


def _slot(row: dict) -> Tuple[str, str]:
    return iso_date(row.get("date")), text(row.get("shift"))


def _operation(own: dict, theirs: dict) -> dict:
    """`bl/changes`' swap, the same operation an approved swap applies."""
    return {
        "action": OP_SWAP,
        "employee": text(own.get("employee")),
        "shift": text(own.get("shift")),
        "date": iso_date(own.get("date")),
        "with_employee": text(theirs.get("employee")),
        "with_shift": text(theirs.get("shift")),
        "with_date": iso_date(theirs.get("date")),
    }


def _option(own: dict, theirs: dict, fixes: List[str]) -> dict:
    return {
        "mine": _shift(own),
        "colleague": text(theirs.get("employee")),
        "theirs": _shift(theirs),
        "fixes": [item for item in fixes if item],
    }


def _shift(row: dict) -> dict:
    return {
        "assignment_id": text(row.get("id")),
        "date": iso_date(row.get("date")),
        "weekday": hebrew_weekday(_day(row)),
        "shift": text(row.get("shift")),
    }
