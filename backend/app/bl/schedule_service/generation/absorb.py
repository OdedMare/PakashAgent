"""Absorbing a new soldier or a new shift into the drafts already built.

A saved profile that gained a person or a shift used to apply only to the
next build. Now each draft still ahead of today is refit in place: a range
job with `keep_existing` from today (or the draft's first day) to its end,
so the newcomer takes shifts only from whoever carries more than their
share, a new shift's slots are added and filled, and every other row stays
where it was (`solver/stability.py`). A published week is never touched —
it is listed as skipped so the manager can decide. A draft with nothing on
it is not solved, since there is no board to absorb into, but a new shift
still gets its empty row there: the board draws rows from the stored grid,
and a week being built by hand would otherwise never show the shift.

Switching a soldier off (`on_duty: false`, the reservists' switch) is the
other direction: their rows in each draft from today on are vacated, each
one logged, and the draft is refit around the gap the same way. Switching
them back on reads as a new soldier. A published week keeps its rows and is
listed as skipped.
"""

from typing import Iterable, List, Optional

from app.bl.schedule_service.constants import ACTION_REMOVED, GENERATION_RUNNING
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.generation.job import GenerationJob
from app.bl.schedule_service.rows import iso, text
from app.bl.scheduler.availability import OFF_DUTY_REASON
from app.bl.shared import switched_off
from app.common.errors import AgentError
from app.common.time_context import israel_today

_PUBLISHED = "הסידור מפורסם; יש להחזיר אותו לטיוטה כדי להטמיע את השינוי"
_BUSY = "בנייה אחרת רצה על הסידור הזה"
# The manager's side of a vacated row (D8): they flipped the switch, nothing more.
OFF_DUTY_CHANGE = "החייל/ת כובה/תה ברשימת כוח האדם"


class ChangeAbsorber:
    def __init__(self, context: ScheduleContext, ranges, runner, today=None):
        self._repository = context.repository
        self._ranges = ranges
        self._runner = runner
        self._today = today or (lambda: israel_today().isoformat())

    def absorb(self, team_id: str, before: Optional[dict], after: dict) -> dict:
        """Refit every draft ahead of today around what the save changed."""
        added = added_to(before, after)
        off = turned_off(before, after)
        result = dict(added, switched_off=off, vacated=0, schedules=[], skipped=[])
        if not added["employees"] and not added["shifts"] and not off:
            return result
        today = self._today()
        for row in self._repository.list_schedules(team_id):
            if iso(row.get("ends_on")) < today:
                continue
            schedule = self._repository.get_schedule(row["id"], team_id)
            first = max(today, iso(schedule.get("starts_on")))
            held = _held_by(schedule, off, first)
            if held and _refusal(schedule) is None:
                self._vacate(team_id, schedule, held)
                result["vacated"] += len(held)
                schedule = self._repository.get_schedule(row["id"], team_id)
            if not (added["employees"] or added["shifts"] or held):
                continue
            if _empty_draft(schedule):
                if added["shifts"]:
                    self._ranges.extend_grid(team_id, schedule, first, iso(schedule.get("ends_on")))
                continue
            self._refit(team_id, schedule, first, result)
        return result

    def _vacate(self, team_id: str, schedule: dict, rows: List[dict]) -> None:
        """A switched-off soldier's shifts from today on, each one logged."""
        for row in rows:
            self._repository.remove_assignment(row["id"], team_id)
            self._repository.append_change(
                team_id, ACTION_REMOVED, schedule_id=schedule["id"],
                employee=text(row.get("employee")), slot_date=iso(row.get("date")),
                shift_name=text(row.get("shift")), reason=OFF_DUTY_CHANGE,
                agent_reason=OFF_DUTY_REASON,
            )

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


def _held_by(schedule: dict, names: List[str], first: str) -> List[dict]:
    """The rows these people hold in this period from `first` on."""
    wanted = set(names)
    return [row for row in schedule.get("assignments") or []
            if text(row.get("employee")) in wanted and iso(row.get("date")) >= first]


def _empty_draft(schedule: dict) -> bool:
    return schedule.get("status") == "draft" and not schedule.get("assignments")


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


def turned_off(before: Optional[dict], after: dict) -> List[str]:
    """The people `after` switches off who were on in `before`."""
    if before is None:
        return []
    was_on = set(_active(before))
    return [text(row.get("name")) for row in after.get("employees") or []
            if isinstance(row, dict) and switched_off(row) and text(row.get("name")) in was_on]


def _active(profile: dict) -> List[str]:
    return [text(row.get("name")) for row in profile.get("employees") or []
            if isinstance(row, dict) and not row.get("inactive_from") and not switched_off(row)]


def _names(rows: Iterable) -> List[str]:
    return [text(row.get("name")) for row in rows or [] if isinstance(row, dict)]


def _new(old: List[str], current: List[str]) -> List[str]:
    known = set(old)
    return [name for name in current if name and name not in known]
