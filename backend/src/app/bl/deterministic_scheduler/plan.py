"""`DayPlan`: one date being filled, greedily and reproducibly."""

import datetime
from typing import List

from app.bl import rotation
from app.bl.audit import (
    CONSECUTIVE, CROSS_ROTATION, DOUBLE_BOOKED, OVER_HOURS, SHORT_REST,
    UNAVAILABLE, audit, constraint_conflicts, counts_toward_staffing,
    load_history,
)
from app.bl.audit.roster import index_shifts, shift_hours
from app.bl.deterministic_scheduler.rows import (
    assignment, eligible, employees, roles, same_slot, text, unique,
)
from app.bl.scheduler import effective_availability
from app.common.errors import AgentError

_BLOCKING_CODES = frozenset({
    CONSECUTIVE, CROSS_ROTATION, DOUBLE_BOOKED, OVER_HOURS, SHORT_REST, UNAVAILABLE,
})


class DayPlan:
    def __init__(self, profile: dict, day: str, slots: List[dict], availability, already_scheduled):
        self.profile, self.day, self.slots = profile, day, slots
        self.employees = employees(profile)
        self.people = {text(row.get("name")): row for row in self.employees}
        self.shifts = (profile or {}).get("shifts") or []
        self.availability = effective_availability(profile, availability, day, day)
        self.slot_keys = {(slot["shift_name"], slot["slot_date"]) for slot in slots}
        committed = [row for row in map(assignment, already_scheduled or []) if row]
        # A targeted shift rebuild preserves the other shifts on the same date.
        self.current = [row for row in committed if not self._in_plan(row)]
        self.loads = {}
        self.notes: List[str] = []

    def _in_plan(self, row: dict) -> bool:
        return row["date"] == self.day and (row["shift"], row["date"]) in self.slot_keys

    def pin(self, required_assignments) -> None:
        """Required rows are pins, validated before anything is filled."""
        pinned = []
        for raw in required_assignments or []:
            row = assignment(raw)
            if row is None or (row["shift"], row["date"]) not in self.slot_keys:
                continue
            self._check_pin(row)
            row["reason"] = text(raw.get("reason")) or "שיבוץ חובה של המנהל"
            pinned.append(row)
        self.current.extend(unique(pinned))

    def _check_pin(self, row: dict) -> None:
        if row["employee"] not in self.people:
            raise AgentError("עובד/ת בשיבוץ החובה לא נמצא/ה בצוות")
        if not eligible(self.people[row["employee"]], row["shift"]):
            raise AgentError("%s אינו/ה כשיר/ה למשמרת %s" % (row["employee"], row["shift"]))
        if self._hard_conflict(row, self.slots):
            raise AgentError(
                "שיבוץ החובה של %s ב-%s סותר אילוץ קשיח, סבב או תלתון"
                % (row["employee"], self.day)
            )

    def fill(self, history) -> None:
        """Scarce and specialised slots first; stable tie-breakers make a
        rerun of the same day produce the same result."""
        rows = load_history(list(history or []) + self.current, self.shifts, self.employees)
        self.loads = {row["employee"]: row["hours"] for row in rows}
        self.slots.sort(key=lambda slot: (
            self._legal_count(slot),
            not bool(slot.get("required_roles")),
            not bool(slot.get("requires_shift_manager")),
            slot.get("start_time") or "",
            slot["shift_name"],
        ))
        for slot in self.slots:
            self._fill_slot(slot)

    def _fill_slot(self, slot: dict) -> None:
        while self._counted_on(slot) < max(0, int(slot.get("headcount") or 0)):
            candidates = self._candidates(slot)
            if not candidates:
                self.notes.append(
                    "לא נמצא שיבוץ חוקי ל%s בתאריך %s; המשמרת נשארה בחוסר."
                    % (slot["shift_name"], self.day)
                )
                return
            _, chosen, person = min(candidates, key=lambda item: item[0])
            chosen["reason"] = self._reason(person, slot)
            self.current.append(chosen)
            hours = shift_hours(index_shifts(self.shifts).get(chosen["shift"]) or {})
            self.loads[chosen["employee"]] = self.loads.get(chosen["employee"], 0.0) + hours

    def _candidates(self, slot: dict) -> list:
        found = []
        for name, person in self.people.items():
            if not counts_toward_staffing(person, self.profile) or not eligible(person, slot["shift_name"]):
                continue
            if any(row["employee"] == name and same_slot(row, slot) for row in self.current):
                continue
            row = {"employee": name, "shift": slot["shift_name"], "date": slot["slot_date"], "reason": ""}
            if self._hard_conflict(row, self.slots) or self._introduces_blocking(row):
                continue
            found.append((self._candidate_key(slot, person, self.loads.get(name, 0.0)), row, person))
        return found

    def _candidate_key(self, slot: dict, person: dict, hours: float) -> tuple:
        """Unmet mandatory capabilities first, then the closing group, then
        the lightest accumulated load."""
        missing = self._missing_roles(self.current, slot)
        covers_roles = len(missing.intersection(roles(person)))
        manager_missing = bool(slot.get("requires_shift_manager")) and not any(
            self._person(row["employee"]).get("is_shift_manager")
            for row in self.current if same_slot(row, slot)
        )
        covers_manager = manager_missing and bool(person.get("is_shift_manager"))
        closing = rotation.holds(
            self.profile, person, datetime.date.fromisoformat(slot["slot_date"]), slot["shift_name"]
        )
        remaining = len(missing) - covers_roles + int(manager_missing and not covers_manager)
        return (remaining, not covers_manager, -covers_roles, not closing,
                float(hours), text(person.get("name")))

    def _introduces_blocking(self, row: dict) -> bool:
        warnings = audit(
            self.current + [row], self.shifts, self.employees, self.availability,
            self.profile, self.slots,
        )
        return any(
            item.get("severity") == "warning"
            and item.get("code") in _BLOCKING_CODES
            and item.get("date") in (None, "", row["date"])
            and item.get("employee") in (None, "", row["employee"])
            for item in warnings
        )

    def _hard_conflict(self, row: dict, slots: List[dict]) -> bool:
        slot = next((item for item in slots if same_slot(row, item)), {})
        candidate = dict(row, start_time=slot.get("start_time"), end_time=slot.get("end_time"))
        return any(
            item.get("is_hard", True) is not False and constraint_conflicts(candidate, item)
            for item in self.availability if isinstance(item, dict)
        )

    def _legal_count(self, slot: dict) -> int:
        return sum(
            eligible(person, slot["shift_name"]) and not self._hard_conflict(
                {"employee": name, "shift": slot["shift_name"], "date": slot["slot_date"]}, [slot],
            )
            for name, person in self.people.items()
        )

    def _reason(self, person: dict, slot: dict) -> str:
        day = datetime.date.fromisoformat(slot["slot_date"])
        if rotation.holds(self.profile, person, day, slot["shift_name"]):
            group = text(person.get("rotation_group"))
            pattern = rotation.exit_pattern(self.profile, person)
            cycle = pattern if pattern in ("round", "triplet") else _cycle(self.profile, group)
            return "%s סוגר/ת במועד הזה; השיבוץ עומד במחזור המחייב." % (
                rotation.label(cycle, group) or "קבוצת הסגירה"
            )
        if slot.get("requires_shift_manager") and person.get("is_shift_manager"):
            return "שובץ/ה כמפקד/ת המשמרת, לפי זמינות ואיזון עומס."
        matched = sorted(self._missing_roles([], slot).intersection(roles(person)))
        if matched:
            return "שובץ/ה לתפקיד %s, לפי זמינות ואיזון עומס." % ", ".join(matched)
        return "שובץ/ה לפי זמינות, כשירות ואיזון עומס."

    def _counted_on(self, slot: dict) -> int:
        return sum(
            same_slot(row, slot)
            and counts_toward_staffing(self.people.get(row["employee"], {}), self.profile)
            for row in self.current
        )

    def _missing_roles(self, rows: List[dict], slot: dict) -> set:
        present = set()
        for row in rows:
            if same_slot(row, slot):
                present.update(roles(self._person(row["employee"])))
        return set(slot.get("required_roles") or []) - present

    def _person(self, name: str) -> dict:
        return self.people.get(name, {})

    def final(self) -> List[dict]:
        return [row for row in self.current if self._in_plan(row)]

    def warnings(self) -> List[dict]:
        return [
            row for row in audit(
                self.current, self.shifts, self.employees, self.availability,
                self.profile, self.slots,
            )
            if row.get("date") in (None, "", self.day)
        ]


def _cycle(profile: dict, group: str) -> str:
    if group == "ג":
        return "triplet"
    mode = text(((profile or {}).get("workplace") or {}).get("rotation_mode"))
    return mode if mode in ("round", "triplet") else "round"
