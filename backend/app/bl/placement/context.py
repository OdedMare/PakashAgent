"""One schedule, prepared once, asked "would this placement warn?" many times."""

from typing import Dict, List, Optional

from app.bl.audit import audit
from app.bl.placement import values
from app.bl.shared import warning_key
from app.bl.scheduler import effective_availability


def effective_rows(
    schedule: dict, profile: dict, availability: Optional[List[dict]],
    fallback_day: str,
) -> List[dict]:
    starts_on = values.iso((schedule or {}).get("starts_on")) or fallback_day
    ends_on = values.iso((schedule or {}).get("ends_on")) or fallback_day
    return effective_availability(profile, list(availability or []), starts_on, ends_on)


class PlacementContext:
    """The schedule, roster and constraints a set of placement checks share.

    Built once per question, so asking about every colleague as a candidate
    does not re-derive the vocabulary, the grid and the constraints per name.
    """

    def __init__(
        self, schedule: dict, profile: dict, availability: List[dict],
        moving_assignment_id: str = "",
    ):
        self.schedule = schedule
        self.profile = profile
        self.availability = availability
        self.moving = moving_assignment_id
        self.shifts = values.shifts(profile)
        self.employees = values.employees(profile)
        self.slots = values.slots(schedule)
        self._rows = values.rows(schedule, drop=moving_assignment_id)
        self._by_employee: Dict[str, List[dict]] = {}
        self._by_slot: Dict[tuple, List[dict]] = {}
        for row in self._rows:
            self._by_employee.setdefault(row["employee"], []).append(row)
            self._by_slot.setdefault((row["shift"], row["date"]), []).append(row)
        self._grid: Dict[tuple, List[dict]] = {}
        for slot in self.slots or []:
            if isinstance(slot, dict):
                key = (values.text(slot.get("shift_name")), values.iso(slot.get("slot_date")))
                self._grid.setdefault(key, []).append(slot)

    def verdict(self, employee: str, shift_name: str, slot_date: str) -> dict:
        """Whether a placement warns, without looking for a way out.

        Audits the schedule as the placement would leave it and keeps only
        the warnings this placement introduced: a warning already true of the
        stored schedule is the board's standing state, and attributing it to
        the drag would teach the manager to ignore the dialog.
        """
        before, slots = self._scope(employee, shift_name, slot_date)
        after = before + [{"employee": employee, "shift": shift_name, "date": slot_date}]
        existing = {warning_key(row) for row in self._audit(before, slots)}
        caused = [row for row in self._audit(after, slots) if warning_key(row) not in existing]
        # `audit.py` writes Hebrew already; rewording it would be a second
        # voice describing the same fact.
        reasons = [values.text(row.get("message")) for row in caused]
        blocking = any(
            (row.get("details") or {}).get("constraint_type") == "duty"
            for row in caused
        )
        eligible = values.is_eligible(self.profile, employee, shift_name, slot_date)
        if not eligible:
            # Not an audit warning -- eligibility is a fact about the roster,
            # not the week -- but to the manager it is the same kind of
            # information: a reason this placement is odd.
            reasons.insert(0, (
                "%s לא מוגדר/ת למשמרת %s בפרופיל של מקום העבודה."
                % (employee, shift_name)
            ))
        return {
            "ok": not reasons,
            # Always false. Stated rather than omitted so a caller reading
            # this contract sees that refusing is not on the table (D3).
            "blocking": blocking,
            "reasons": reasons,
            "warnings": caused,
            "eligible": eligible,
        }

    def clean(self, employee: str, shift_name: str, slot_date: str) -> bool:
        """Whether this candidate would warn. An option that warns is not an
        alternative, so a candidate is kept only when it introduces nothing."""
        return self.verdict(employee, shift_name, slot_date)["ok"]

    def _scope(self, employee: str, shift_name: str, slot_date: str):
        """The rows and grid one placement can change a warning on.

        Every audit check is about one person (hours, rest, runs, rotation,
        constraints) or one slot (headcount, roles, commander). Adding one
        row can only move the placed person's warnings and the target
        slot's, so auditing the person's rows plus everyone on that slot,
        before and after, yields exactly the warnings a whole-schedule
        audit would attribute to it. A whole-schedule audit per candidate
        is what made a 70-person replacement search run for minutes.
        """
        target = (shift_name, slot_date)
        rows = list(self._by_employee.get(employee, []))
        rows += [row for row in self._by_slot.get(target, []) if row["employee"] != employee]
        if not self.slots:
            return rows, self.slots
        pairs = {(row["shift"], row["date"]) for row in rows} | {target}
        grid = [slot for pair in pairs for slot in self._grid.get(pair, [])]
        # An empty grid would make the staffing check grade the rows' own
        # slots from the profile, which the stored grid never asked for; one
        # untouched grid slot keeps it reading the grid and reports the same
        # thing before and after.
        return rows, grid or self.slots[:1]

    def _audit(self, assignments: List[dict], slots) -> List[dict]:
        return audit(
            assignments, self.shifts, self.employees, self.availability,
            self.profile, slots,
        )
