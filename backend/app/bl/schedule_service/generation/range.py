"""Building a run of dates inside a period that already exists."""

from typing import List

from app.bl.scheduler import plan_spans
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.generation.job import GenerationJob
from app.bl.schedule_service.profile_gate import ProfileGate
from app.bl.schedule_service.rows import iso
from app.common.errors import AgentError


class RangeBuilder:
    def __init__(self, context: ScheduleContext, gate: ProfileGate):
        self._context = context
        self._repository = context.repository
        self._gate = gate

    def start_range_generation(
        self,
        team_id: str,
        schedule_id: str,
        starts_on: str,
        ends_on: str,
        instructions: str = "",
    ) -> dict:
        """Prepare a run of dates inside an existing draft for generation.

        `start_day_generation` over more than one date, and bound by the same
        contract: manager-placed rows on those dates are pins the agent fills
        around, generated and imported rows there are replaced, and every
        date outside the run stays untouched. No list of required assignments
        is taken, because the board already is that list — whatever was
        placed by hand is carried into each span as it is reached.
        """
        schedule = self._repository.get_schedule(schedule_id, team_id)
        if schedule.get("status") != "draft":
            raise AgentError("יש להחזיר את הסידור לטיוטה לפני בניית ימים בו")
        spans = self._spans(team_id, schedule, iso(starts_on), iso(ends_on))
        job = GenerationJob.open(
            spans,
            total_days=sum(len(span["dates"]) for span in spans),
            instructions=instructions,
            required=[],
        )
        return self._context.view(
            self._repository.set_generation(schedule_id, team_id, job.to_dict()),
            team_id,
        )

    def _spans(
        self, team_id: str, schedule: dict, first: str, last: str
    ) -> List[dict]:
        """The spans to ask for: planned from the profile, held to the grid.

        A period opened before the vocabulary changed has the rows it was
        opened with, and a date it never had is not one this job can write to.
        """
        if not first or not last or first > last:
            raise AgentError("טווח התאריכים אינו תקין")
        stored = {
            iso(slot.get("slot_date")) for slot in schedule.get("slots") or []
        }
        wanted = sorted(day for day in stored if first <= day <= last)
        if not wanted:
            raise AgentError("אין משמרות בסידור הזה בתאריכים שנבחרו")
        planned = plan_spans(self._gate.buildable_profile(team_id), wanted[0], wanted[-1])
        spans = _within(planned, stored)
        if not spans:
            raise AgentError("אף משמרת מוגדרת לא חלה בתאריכים שנבחרו")
        return spans


def _within(spans: List[dict], stored: set) -> List[dict]:
    """Planned spans, kept to the dates the stored grid actually has."""
    kept = []
    for span in spans:
        dates = [day for day in span["dates"] if day in stored]
        if dates:
            kept.append({"date": dates[0], "through": dates[-1], "dates": dates})
    return kept
