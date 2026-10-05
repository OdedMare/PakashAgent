"""Placing someone: what it would cost, and who else could take the slot."""

from app.bl.placement import check as check_placement
from app.bl.placement import closure_of, suggest_alternatives
from app.bl.tools.period_tools import Tool
from app.bl.tools.values import assignment_id, iso, text, window
from app.common.errors.errors import AgentError

# How many candidates a replacement search returns. Past a handful the list
# stops being an answer and becomes a second grid to read.
_MAX_CANDIDATES = 5
_RANKED_BY = (
    "לפי שעות מצטברות בתקופה — הקל/ה ביותר ראשון/ה, "
    "אחרי סינון של כל מי שהשיבוץ היה יוצר אצלו/ה אזהרה."
)
_NO_PERIOD = "אין סידור מאוחסן לתאריך הזה"


class ValidatePlacement(Tool):
    """What placing this person on this slot would cost. Writes nothing.

    `bl/placement.py` verbatim — the same call the board makes for a drag, so
    the *agent* is held to the same answer. **It does not gate**: `blocking`
    comes back false however bad the news (D3).
    """

    def __call__(
        self, team_id: str, employee: str, shift_name: str, slot_date: str,
        schedule_id: str = "", moving_assignment_id: str = "",
    ) -> dict:
        if not text(employee):
            raise AgentError("צריך לציין שם עובד")
        if not text(slot_date):
            raise AgentError("צריך לציין תאריך")
        schedule = self._reads.schedule(team_id, schedule_id=schedule_id, day=slot_date)
        if schedule is None:
            return {"found": False, "reason": _NO_PERIOD}
        verdict = check_placement(
            schedule,
            self._reads.profile(team_id),
            employee=text(employee),
            shift_name=text(shift_name),
            slot_date=iso(slot_date),
            availability=self._reads.availability(team_id, window(schedule)),
            moving_assignment_id=text(moving_assignment_id),
        )
        return dict(verdict, found=True, schedule_id=text(schedule.get("id")))


class FindReplacements(Tool):
    """Who could take this slot, ranked, each carrying its own reason.

    `employee` is the person coming *off* -- their row is taken out of the
    hypothetical first, so a colleague is not rejected for a double-booking
    the replacement itself resolves. **Every candidate is re-validated**
    through `placement.suggest_alternatives`, which keeps only options that
    introduce no warning of their own.
    """

    def __call__(
        self, team_id: str, shift_name: str, slot_date: str,
        employee: str = "", schedule_id: str = "",
    ) -> dict:
        if not text(slot_date):
            raise AgentError("צריך לציין תאריך")
        schedule = self._reads.schedule(team_id, schedule_id=schedule_id, day=slot_date)
        if schedule is None:
            return {"found": False, "candidates": [], "reason": _NO_PERIOD}
        profile = self._reads.profile(team_id)
        leaving, shift, date = text(employee), text(shift_name), iso(slot_date)
        alternatives = suggest_alternatives(
            schedule,
            profile,
            employee=leaving,
            shift_name=shift,
            slot_date=date,
            availability=self._reads.availability(team_id, window(schedule)),
            moving_assignment_id=assignment_id(schedule, leaving, shift, date),
        )
        return {
            "found": True,
            "schedule_id": text(schedule.get("id")),
            "shift": shift,
            "date": date,
            "replacing": leaving,
            "candidates": (alternatives.get("employees") or [])[:_MAX_CANDIDATES],
            # Where this person could go instead, when the question turns out
            # to be "move them" rather than "replace them".
            "other_slots": alternatives.get("slots") or [],
            # On a closure the replacement comes from the group already in,
            # and an answer that did not say so would read as a free choice.
            "closure": closure_of(profile, date, shift),
            "ranked_by": _RANKED_BY,
        }
