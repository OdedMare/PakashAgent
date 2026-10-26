"""Absorbing a new soldier or a new shift into the drafts already built.

A saved profile that gained a person or a shift used to apply only to the
next build. Now each draft still ahead of today is refit in place: a range
job with `keep_existing` from today (or the draft's first day) to its end,
so the newcomer takes shifts only from whoever carries more than their
share, a new shift's slots are added and filled, and every other row stays
where it was (`solver/stability.py`). A published week is never touched —
it is listed as skipped so the manager can decide — and neither is a draft
with nothing on it, which is not a board to absorb anything into.
"""

from typing import Iterable, List, Optional

from app.bl.schedule_service.constants import GENERATION_RUNNING
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.generation.job import GenerationJob
from app.bl.schedule_service.rows import iso, text
from app.common.errors import AgentError
from app.common.time_context import israel_today

_PUBLISHED = "הסידור מפורסם; יש להחזיר אותו לטיוטה כדי להטמיע את השינוי"
_BUSY = "בנייה אחרת רצה על הסידור הזה"


class ChangeAbsorber:
    def __init__(self, context: ScheduleContext, ranges, runner, today=None):
        self._repository = context.repository
        self._ranges = ranges
        self._runner = runner
        self._today = today or (lambda: israel_today().isoformat())

    def absorb(self, team_id: str, before: Optional[dict], after: dict) -> dict:
        """Refit every draft ahead of today around what the save added."""
        added = added_to(before, after)
        result = dict(added, schedules=[], skipped=[])
        if not added["employees"] and not added["shifts"]:
            return result
        today = self._today()
        for row in self._repository.list_schedules(team_id):
            if iso(row.get("ends_on")) < today:
                continue
            schedule = self._repository.get_schedule(row["id"], team_id)
            self._refit(team_id, schedule, max(today, iso(schedule.get("starts_on"))), result)
        return result

    def _refit(self, team_id: str, schedule: dict, first: str, result: dict) -> None:
        span = {"schedule_id": schedule["id"], "starts_on": first,
                "ends_on": iso(schedule.get("ends_on"))}
        reason = _refusal(schedule)
        if reason is None:
            try:
                self._ranges.start_range_generation(
                    team_id, schedule["id"], span["starts_on"], span["ends_on"],
                    keep_existing=True)
                self._runner.queue(team_id, schedule["id"])
            except AgentError as exc:
                reason = str(exc)
        if reason is None:
            result["schedules"].append(span)
        elif reason:
            result["skipped"].append(dict(span, reason=reason))


def _refusal(schedule: dict) -> Optional[str]:
    """Why this draft is not refit; "" to leave it out silently."""
    if not schedule.get("assignments"):
        return ""
    if schedule.get("status") != "draft":
        return _PUBLISHED
    if GenerationJob.of(schedule).status == GENERATION_RUNNING:
        return _BUSY
    return None


def added_to(before: Optional[dict], after: dict) -> dict:
    """The active people and the shifts `after` has and `before` did not."""
    if before is None:
        return {"employees": [], "shifts": []}
    return {
        "employees": _new(_active(before), _active(after)),
        "shifts": _new(_names(before.get("shifts")), _names(after.get("shifts"))),
    }


def _active(profile: dict) -> List[str]:
    return [text(row.get("name")) for row in profile.get("employees") or []
            if isinstance(row, dict) and not row.get("inactive_from")]


def _names(rows: Iterable) -> List[str]:
    return [text(row.get("name")) for row in rows or [] if isinstance(row, dict)]


def _new(old: List[str], current: List[str]) -> List[str]:
    known = set(old)
    return [name for name in current if name and name not in known]
