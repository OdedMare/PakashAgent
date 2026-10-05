"""Schedule persistence: periods, slots, assignments, constraints, history.

Every read is scoped by `team_id`, and the team is a required argument rather
than an optional filter. A schedule id is a UUID and therefore hard to guess,
but "hard to guess" is not an access control -- one workspace's manager
holding another's schedule id must still get a `NotFoundError`, and a miss
across teams is never distinguished from a miss outright
([D10](../../../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).

Two invariants are enforced here rather than left to callers:

- **`assignments.reason` is never blank** (D8) — see `assignments.py`.
- **`change_log` is append-only** (D4) — see `records.py`.

`ScheduleRepository` composes one mixin per table group, the same way
`Repository` composes the per-concern repositories.
"""

import datetime
from typing import Optional

from app.common.time_context import israel_today
from app.dal.repository.assignments import AssignmentRepository
from app.dal.repository.periods import PeriodRepository
from app.dal.repository.records import (
    AvailabilityRepository, ChangeLogRepository, PreferenceRepository,
)
from app.dal.repository.schedule_vocabulary import (  # noqa: F401
    ASSIGNED_BY_AGENT,
    ASSIGNED_BY_IMPORT,
    ASSIGNED_BY_MANAGER,
    PREFERENCE_ACTIVE,
    PREFERENCE_ARCHIVED,
    PREFERENCE_EMPLOYEE,
    PREFERENCE_GENERAL,
    PREFERENCE_NOTIFICATION,
    PREFERENCE_SHIFT,
    PREFERENCE_STAFFING,
    PREFERENCE_SUGGESTED,
    SOURCE_AGENT,
    SOURCE_EMPLOYEE_REPORTED,
    SOURCE_INTERVIEW,
    SOURCE_MANAGER,
)


class ScheduleRepository(
    PeriodRepository, AssignmentRepository, AvailabilityRepository,
    PreferenceRepository, ChangeLogRepository,
):
    """Periods, assignments, constraints, preferences and the change log."""


def week_bounds(day: Optional[datetime.date] = None) -> tuple:
    """The Sunday-to-Saturday week containing `day`, as ISO strings.

    Sunday-based because the workweek here is Israeli: the source files run
    ראשון through שבת, and a Monday-based week would split every one of them
    across two schedules.
    """
    day = day or israel_today()
    # `weekday()` is Monday=0; Sunday is 6, so this rolls back to Sunday.
    start = day - datetime.timedelta(days=(day.weekday() + 1) % 7)
    return start.isoformat(), (start + datetime.timedelta(days=6)).isoformat()


__all__ = [
    "ScheduleRepository", "week_bounds",
    "SOURCE_MANAGER", "SOURCE_AGENT", "SOURCE_EMPLOYEE_REPORTED",
    "SOURCE_INTERVIEW",
]
