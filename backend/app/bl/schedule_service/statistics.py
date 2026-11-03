"""The stats panel's numbers for any span of dates, optionally one person's."""

import datetime
from typing import Callable, List

from app.bl.audit import in_window, shift_stats, warning_in_window
from app.bl.schedule_service import rows
from app.bl.schedule_service.context import ScheduleContext


class StatsReader:
    """`shift_stats` over a day, a week, a month or a range the manager chose.

    The overview already carries the current period's numbers. This answers
    the same question for a span that is not a stored period -- a single day
    inside one, or a month across several -- and for one person within it.

    Nothing is recounted differently here: the periods arrive audited exactly
    as the board draws them, their rows are narrowed to the span, and the one
    function the overview uses does the arithmetic. So a span that happens to
    be a whole period reports that period's own figures, and a finding
    counted here is one printed under the calendar
    ([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
    """

    def __init__(self, context: ScheduleContext, periods_between: Callable):
        self._context = context
        self._periods_between = periods_between

    def between(
        self, team_id: str, start: str, end: str, employee: str = ""
    ) -> dict:
        # Validates the span, and refuses one too wide to audit in a request.
        periods = self._periods_between(team_id, start, end)
        first, last = _iso(start), _iso(end)
        profile = self._context.profile(team_id)
        assignments: List[dict] = []
        slots: List[dict] = []
        warnings: List[dict] = []
        for period in periods:
            assignments += [
                fact for fact in rows.assignment_facts(period.get("assignments"))
                if in_window(fact["date"], first, last)
            ]
            slots += [
                slot for slot in map(rows.stats_slot, period.get("slots") or [])
                if in_window(slot["slot_date"], first, last)
            ]
            warnings += [
                item for item in period.get("warnings") or []
                if warning_in_window(item, first, last)
            ]
        return shift_stats(
            assignments,
            rows.shifts(profile),
            rows.employees(profile),
            slots=slots,
            warnings=warnings,
            profile=profile,
            availability=self._context.availability_facts(
                team_id, {"starts_on": first, "ends_on": last}, with_reason=False
            ),
            employee=rows.text(employee),
            duties=self._context.complex_duties(team_id, first, last),
        )


def _iso(value: str) -> str:
    """A validated request date in the one spelling the rows compare against."""
    return datetime.date.fromisoformat(rows.iso(value)).isoformat()
