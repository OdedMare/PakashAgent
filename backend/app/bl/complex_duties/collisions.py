"""A duty set on a shift the soldier already holds: vacate it and refill.

The duty is saved either way (the commander decides the מכלול; §4 of the
plan). What happens to the shift depends on the week:

- **A draft, today or later**: the soldier is taken off the shift -- logged
  with the duty as its reason, like any manual removal (D18) -- and the
  dates and shifts it touched are rebuilt as a range job that keeps every
  other row where it is (`keep_existing`, D37). The solver fills the seat
  around the board and can no longer place the soldier there, since the
  duty is now hard unavailability.
- **A published week** is never changed. The team's commander is told,
  in the notice, who is on duty and on which shift, to find the cover.
- **A date already past** is left as it stood.

The removals and the rebuild are the משמרת's own writes; they are made as
the commander (D43) and are told to the team like every other one.
"""

import datetime
from typing import Callable, Dict, List

from app.common.actor import acting_as
from app.common.errors import AppError
from app.common.time_context import israel_today

VACATED = "vacated"        # taken off, and the seat is being refilled
VACATED_ONLY = "vacated_only"  # taken off; the refill could not be opened
PUBLISHED = "published"    # left on a published week: the team finds cover
PAST = "past"              # already past: left as it stood

_VACATED_NOTICE = "הוריד חייל ממשמרת בגלל תורנות מכלול, והמשבצת מושלמת מחדש"


class DutyCollisions:
    def __init__(self, schedules, notify: Callable[[str, str, str], None],
                 today: Callable[[], str] = None):
        self._schedules = schedules
        self._notify = notify
        self._today = today or (lambda: israel_today().isoformat())

    def resolve(self, complex_id: str, conflicts: List[dict]) -> List[dict]:
        """Each conflict with its `outcome`. Draft rows are grouped per
        schedule, so a whole approved fill opens one rebuild per week."""
        if self._schedules is None:
            return [dict(row, outcome=PUBLISHED if row["status"] == "published" else PAST)
                    for row in conflicts]
        today = self._today()
        drafts: Dict[tuple, List[dict]] = {}
        done = []
        with acting_as("commander:" + complex_id):
            for row in conflicts:
                if row["date"] < today:
                    done.append(dict(row, outcome=PAST))
                elif row["status"] == "published":
                    done.append(dict(row, outcome=PUBLISHED))
                    self._notify(row["team_id"], complex_id, _published(row))
                elif self._vacate(row):
                    drafts.setdefault((row["team_id"], row["schedule_id"]), []).append(row)
                else:
                    done.append(dict(row, outcome=VACATED_ONLY))
            for (team_id, schedule_id), rows in drafts.items():
                outcome = VACATED if self._refill(team_id, schedule_id, rows) else VACATED_ONLY
                done += [dict(row, outcome=outcome) for row in rows]
                self._notify(team_id, complex_id, _VACATED_NOTICE)
        return done

    def _vacate(self, row: dict) -> bool:
        try:
            self._schedules.unassign(
                row["team_id"], row["assignment_id"],
                reason="תורנות מכלול: %s" % row.get("duty_type", ""),
                schedule_id=row["schedule_id"],
            )
            return True
        except AppError:
            return False

    def _refill(self, team_id: str, schedule_id: str, rows: List[dict]) -> bool:
        dates = sorted(row["date"] for row in rows)
        try:
            self._schedules.start_range_generation(
                team_id, schedule_id, dates[0], dates[-1],
                shifts=sorted({row["shift_name"] for row in rows}),
                keep_existing=True,
            )
            self._schedules.queue_generation(team_id, schedule_id)
            return True
        except AppError:
            # Another build already running on the week, most often: the
            # seat stays empty and the board shows it unfilled.
            return False


def _published(row: dict) -> str:
    return "תורנות מכלול: %s משובץ/ת ל%s ב־%s בשבוע שפורסם — יש למצוא מחליף" % (
        row["employee"], row["shift_name"], _display(row["date"]))


def _display(iso: str) -> str:
    try:
        return datetime.date.fromisoformat(iso).strftime("%d/%m")
    except ValueError:
        return iso
