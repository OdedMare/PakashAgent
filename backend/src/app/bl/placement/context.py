"""One schedule, prepared once, asked "would this placement warn?" many times."""

from typing import List, Optional

from app.bl.audit import audit
from app.bl.placement import values
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

    def verdict(self, employee: str, shift_name: str, slot_date: str) -> dict:
        """Whether a placement warns, without looking for a way out.

        Audits the schedule as the placement would leave it and keeps only
        the warnings this placement introduced: a warning already true of the
        stored schedule is the board's standing state, and attributing it to
        the drag would teach the manager to ignore the dialog.
        """
        before = values.rows(self.schedule, drop=self.moving)
        after = before + [{"employee": employee, "shift": shift_name, "date": slot_date}]
        existing = {values.warning_key(row) for row in self._audit(before)}
        caused = [row for row in self._audit(after) if values.warning_key(row) not in existing]
        # `audit.py` writes Hebrew already; rewording it would be a second
        # voice describing the same fact.
        reasons = [values.text(row.get("message")) for row in caused]
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
            "blocking": False,
            "reasons": reasons,
            "warnings": caused,
            "eligible": eligible,
        }

    def clean(self, employee: str, shift_name: str, slot_date: str) -> bool:
        """Whether this candidate would warn. An option that warns is not an
        alternative, so a candidate is kept only when it introduces nothing."""
        return self.verdict(employee, shift_name, slot_date)["ok"]

    def _audit(self, assignments: List[dict]) -> List[dict]:
        return audit(
            assignments, self.shifts, self.employees, self.availability,
            self.profile, self.slots,
        )
