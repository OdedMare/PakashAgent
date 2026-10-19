"""One person's own view: hours, shifts, teammates, and what changed (D16)."""

from typing import Any, Dict, List

from app.bl.audit import personal_summary
from app.bl.employee_service.values import (
    iso_date, shifts, text, window,
)

# How many of the newest change-log rows are searched, and how many naming
# this person are kept.
_LOG_SCAN = 200
_LOG_KEEP = 40


class PersonalView:
    def __init__(self, repository, schedules, swaps):
        self._repository = repository
        # The schedule service rather than the repository: the personal view
        # needs an *audited* schedule, and re-deriving the audit here would be
        # a second implementation of it.
        self._schedules = schedules
        self._swaps = swaps

    def me(self, team_id: str, employee: str) -> dict:
        """Everything the personal area opens with, in one call.

        `employee` comes from the signed cookie and never from the request,
        which is the whole access control of this screen. Only a *published*
        schedule is read: hours the manager is still moving around are not
        yet a commitment.
        """
        profile = self._repository.team_profile(team_id) or {}
        schedule = self._schedules.current(team_id, role="member")
        assignments = (schedule or {}).get("assignments") or []
        changes = self._changes(team_id, employee)
        return {
            "employee": employee,
            "schedule": schedule,
            "summary": self._summary(team_id, employee, schedule, profile),
            # Who else is on each of their shifts, read off the same grid.
            "teammates": teammates(assignments, employee),
            "requests": self._repository.list_requests(team_id, employee=employee),
            "swaps": self._swaps.my_swaps(team_id, employee),
            # "Somebody is waiting on you" is a different badge from
            # "something moved", and folding them would hide the deadline.
            "swaps_awaiting_me": len(self._swaps.incoming_swaps(team_id, employee)),
            # Only the log entries naming this person; the full log carries
            # other people's stated reasons.
            "changes": changes,
            "unseen": sum(1 for row in changes if row.get("is_new")),
            "shifts": shifts(profile),
        }

    def acknowledge(self, team_id: str, employee: str) -> dict:
        """Mark what the employee was just shown as read (D16).

        Called by the personal area, not by a login: a login proves only that
        they arrived. Returns the new count so the badge settles at once.
        """
        self._repository.acknowledge(team_id, employee)
        return {"employee": employee, "unseen": 0}

    def _summary(self, team_id: str, employee: str, schedule, profile: dict) -> dict:
        start, end = window(schedule)
        return personal_summary(
            employee,
            (schedule or {}).get("assignments") or [],
            shifts(profile),
            warnings=(schedule or {}).get("warnings") or [],
            availability=self._repository.availability(
                team_id, start, end, employee=employee
            ),
        )

    def _changes(self, team_id: str, employee: str) -> List[dict]:
        identity = self._repository.find_identity(team_id, employee) or {}
        naming = [
            row for row in self._repository.change_log(team_id, limit=_LOG_SCAN)
            if employee in (text(row.get("employee")), text(row.get("replaced_employee")))
        ]
        return mark_unseen(naming[:_LOG_KEEP], identity.get("acknowledged_at"))


def teammates(assignments: List[dict], employee: str) -> List[dict]:
    """Who else is on each shift this person works."""
    mine = {
        (iso_date(row.get("date")), text(row.get("shift")))
        for row in assignments or [] if text(row.get("employee")) == employee
    }
    grouped: Dict[tuple, List[str]] = {}
    for row in assignments or []:
        key = (iso_date(row.get("date")), text(row.get("shift")))
        name = text(row.get("employee"))
        if key in mine and name and name != employee:
            grouped.setdefault(key, []).append(name)
    return [
        {"date": key[0], "shift": key[1], "with": sorted(grouped[key])}
        for key in sorted(grouped)
    ]


def mark_unseen(rows: List[dict], acknowledged_at: Any) -> List[dict]:
    """Flag the log rows that landed after the employee last acknowledged.

    A NULL `acknowledged_at` marks **everything** new rather than nothing:
    the opposite default would swallow exactly the first notification worth
    sending. Compared as `datetime`s, never as text.
    """
    return [dict(row, is_new=_is_new(row.get("created_at"), acknowledged_at)) for row in rows]


def _is_new(created: Any, acknowledged_at: Any) -> bool:
    if acknowledged_at is None or created is None:
        return True
    try:
        return created > acknowledged_at
    except TypeError:
        # Mixed aware/naive timestamps: treat as new rather than dropping the
        # notification on an error nobody would see.
        return True
