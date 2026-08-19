"""The employee's own area: their identity, their hours, their requests.

The business half of [D14](../../../docs/DECISIONS.md#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10).
Three concerns live here:

- **Claiming a name.** An employee turns a share-link visit into an identity
  by picking their name off the workplace roster and setting a passcode. The
  name must be one the interview actually recorded -- a free-text claim would
  let anyone with the link invent a person, and every downstream join is on
  that string.
- **The personal view.** Hours, shifts, warnings and constraints for one
  person, computed by `bl/audit.py` so the employee's arithmetic is literally
  the manager's arithmetic rather than a second implementation of it.
- **Constraint requests.** Submitting, withdrawing, and -- on the manager's
  side -- approving into a real `availability` row.

**Approval is the only thing that writes a constraint.** A pending request is
inert: invisible to the audit, absent from the schedule, and incapable of
moving a number
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
That is what keeps "employees may submit" from becoming "employees may
schedule".
"""

from typing import Any, Dict, List, Optional

from app.bl.audit import fairness, personal_summary
from app.common.errors import AgentError, AuthError
from app.dal.repository.identities import (
    STATUS_APPROVED, STATUS_AWAITING, STATUS_PENDING, STATUS_REJECTED,
)
from app.dal.repository.schedules import SOURCE_EMPLOYEE_REPORTED

# Logged against the change log when a manager rules on a request, so an
# approval is traceable in the same place every other change is (D4).
ACTION_REQUEST_APPROVED = "request_approved"
ACTION_REQUEST_REJECTED = "request_rejected"
# A swap the manager refused. The approval has no action of its own: applying
# it goes through the ordinary swap path in `schedule_service`, which appends
# `ACTION_SWAPPED` exactly as a manager-initiated swap does. Two log rows for
# one swap would make the history read as two moves.
ACTION_SWAP_REJECTED = "swap_rejected"


class EmployeeService:
    def __init__(self, repository, schedules):
        self._repository = repository
        # The schedule service rather than the repository: the personal view
        # needs an *audited* schedule, and re-deriving the audit here would be
        # the second implementation this module exists to avoid.
        self._schedules = schedules

    # -- identity ----------------------------------------------------------

    def roster(self, team_id: str) -> dict:
        """Names available to claim, and which are taken.

        Served to a share-link visitor before they have an identity, so it
        carries names only -- never a passcode hash, never a last-seen time.
        Those are the manager's view, and a claim screen showing when someone
        last signed in tells a stranger with the link more than it should.
        """
        profile = self._repository.team_profile(team_id) or {}
        claimed = set(self._repository.claimed_names(team_id))
        return {
            "names": [
                {"employee": name, "claimed": name in claimed}
                for name in _roster_names(profile)
            ]
        }

    def claim(self, team_id: str, employee: str, passcode: str) -> dict:
        """Bind a roster name to a passcode.

        The name is checked against the workplace profile first. Without that
        check the share link becomes a licence to create people: a claim on
        "מנהל" would be accepted, and every later join on that string would
        quietly match nothing.
        """
        name = (employee or "").strip()
        profile = self._repository.team_profile(team_id) or {}
        if name not in _roster_names(profile):
            raise AgentError("השם אינו מופיע ברשימת העובדים של הצוות")
        self._repository.claim_identity(team_id, name, passcode)
        return {"employee": name}

    def login(self, team_id: str, employee: str, passcode: str) -> dict:
        """Verify a claim. Raises `AuthError` when it does not match."""
        row = self._repository.authenticate_employee(
            team_id, employee, passcode
        )
        return {"employee": row["employee"]}

    def identities(self, team_id: str) -> List[dict]:
        """Every claim, for the manager's roster panel."""
        return self._repository.list_identities(team_id)

    def release(self, team_id: str, employee: str) -> None:
        """Free a claimed name. The manager's tool for a departure."""
        self._repository.release_identity(team_id, employee)

    # -- the personal view -------------------------------------------------

    def me(self, team_id: str, employee: str) -> dict:
        """Everything the personal area opens with, in one call.

        `employee` comes from the signed cookie and never from the request,
        which is the whole access control of this screen: the caller does not
        get to say who they are.

        Only a *published* schedule is read. An employee looking at hours the
        manager is still moving around would be reading a number that is not
        yet a commitment -- and would ask about it.
        """
        profile = self._repository.team_profile(team_id) or {}
        schedule = self._schedules.current(team_id, role="member")
        assignments = (schedule or {}).get("assignments") or []
        warnings = (schedule or {}).get("warnings") or []
        shifts = _shifts(profile)

        window = _window(schedule)
        constraints = self._repository.availability(
            team_id, window[0], window[1], employee=employee
        )
        summary = personal_summary(
            employee, assignments, shifts,
            warnings=warnings, availability=constraints,
        )
        identity = self._repository.find_identity(team_id, employee) or {}
        changes = _mark_unseen(
            [
                row for row in self._repository.change_log(team_id, limit=200)
                if _names(row, employee)
            ][:40],
            identity.get("acknowledged_at"),
        )
        return {
            "employee": employee,
            "schedule": schedule,
            "summary": summary,
            # The comparison that answers "why is it always me". Names and
            # hours only -- it is already visible who works when, so the
            # totals add no exposure the roster does not.
            "fairness": fairness(assignments, shifts, _employees(profile)),
            # Who else is on each of their shifts. Read off the same
            # assignments, so it cannot drift from the grid.
            "teammates": _teammates(assignments, employee),
            "requests": self._repository.list_requests(
                team_id, employee=employee
            ),
            # Only the log entries naming this person. The full change log is
            # the manager's, and it carries other people's stated reasons.
            "changes": changes,
            # What landed since they last acknowledged (D16). The count is
            # what the screen leads with: an employee whose shift moved
            # yesterday should not have to compare a grid against memory to
            # find out.
            "unseen": sum(1 for row in changes if row.get("is_new")),
            "shifts": shifts,
        }

    def acknowledge(self, team_id: str, employee: str) -> dict:
        """Mark what the employee was just shown as read (D16).

        Called by the personal area, not by a login: the point is to record
        that a person *saw* the moves that concern them, and a login proves
        only that they arrived.

        Returns the new count rather than a bare status so the caller can
        settle the badge without a second round trip.
        """
        self._repository.acknowledge(team_id, employee)
        return {"employee": employee, "unseen": 0}

    # -- constraint requests -----------------------------------------------

    def submit(
        self,
        team_id: str,
        employee: str,
        constraint_date: str,
        shift_name: str = "",
        available: bool = False,
        reason: str = "",
    ) -> dict:
        """Submit a constraint request. Writes no constraint.

        Returns the stored request so the UI can show it as pending
        immediately -- the employee needs to see that it landed, and that it
        has not yet been decided.
        """
        return self._repository.submit_request(
            team_id, employee, constraint_date,
            shift_name=(shift_name or "").strip(),
            available=available, reason=(reason or "").strip(),
        )

    def withdraw(self, team_id: str, employee: str, request_id: str) -> dict:
        return self._repository.withdraw_request(
            request_id, team_id, employee
        )

    def my_requests(self, team_id: str, employee: str) -> List[dict]:
        return self._repository.list_requests(team_id, employee=employee)

    # -- the manager's side ------------------------------------------------

    def pending(self, team_id: str) -> List[dict]:
        """Requests awaiting a decision, for the manager's inbox."""
        return self._repository.list_requests(team_id, status=STATUS_PENDING)

    def all_requests(self, team_id: str) -> List[dict]:
        return self._repository.list_requests(team_id)

    def approve(
        self, team_id: str, request_id: str, decided_reason: str = ""
    ) -> dict:
        """Approve a request and promote it into a real constraint.

        Two writes, in this order: the ruling, then the `availability` row it
        creates. The constraint is written with
        `source='employee_reported'` -- the value
        [D13](../../../docs/DECISIONS.md#d13--constraints-are-recorded-by-the-manager-with-their-source-marked)
        already defined for "this came from the employee", which is exactly
        what an approved submission is. Recording it as `manager` would erase
        the provenance the column exists to keep.

        This is the moment the request becomes countable: `audit.py` reads
        `availability`, so the warning about scheduling someone on a day they
        cannot work appears now and not a moment earlier.
        """
        request = self._repository.decide_request(
            request_id, team_id, STATUS_APPROVED, decided_reason
        )
        constraint = self._schedules.set_constraint(
            team_id,
            request["employee"],
            _iso_date(request["constraint_date"]),
            shift_name=request.get("shift_name") or "",
            available=bool(request.get("available")),
            reason=request.get("reason") or "",
            source=SOURCE_EMPLOYEE_REPORTED,
        )
        return {"request": request, "constraint": constraint}

    def reject(
        self, team_id: str, request_id: str, decided_reason: str = ""
    ) -> dict:
        """Reject a request, with a reason the employee will read.

        The reason is required. A rejection that says nothing is how a
        submission channel stops being used -- and the manager already has
        the reason in mind at the moment they click, which is the only moment
        it is cheap to capture (the same argument as
        [D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).
        """
        if not (decided_reason or "").strip():
            raise AgentError("צריך לציין סיבה לדחייה")
        request = self._repository.decide_request(
            request_id, team_id, STATUS_REJECTED, decided_reason.strip()
        )
        self._repository.append_change(
            team_id, ACTION_REQUEST_REJECTED,
            employee=request["employee"],
            slot_date=_iso_date(request["constraint_date"]),
            shift_name=request.get("shift_name") or "",
            reason=decided_reason.strip(),
            agent_reason="בקשת אילוץ נדחתה",
        )
        return {"request": request}


def _roster_names(profile: dict) -> List[str]:
    """Employee names as the interview recorded them.

    Read defensively: the profile is model-produced JSON, so a missing or
    differently-shaped field degrades to an empty roster rather than throwing
    on the login screen.
    """
    employees = (profile or {}).get("employees")
    if not isinstance(employees, list):
        return []
    names = []
    for item in employees:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _employees(profile: dict) -> List[dict]:
    employees = (profile or {}).get("employees")
    return employees if isinstance(employees, list) else []


def _shifts(profile: dict) -> List[dict]:
    shifts = (profile or {}).get("shifts")
    return shifts if isinstance(shifts, list) else []


def _teammates(assignments: List[dict], employee: str) -> List[dict]:
    """Who else is on each shift this person works.

    Answers a question people actually ask before a shift, and needs no new
    data -- the roster is already visible to the whole team.
    """
    mine = set()
    for row in assignments or []:
        if _text(row.get("employee")) == employee:
            mine.add((_iso_date(row.get("date")), _text(row.get("shift"))))
    grouped: Dict[tuple, List[str]] = {}
    for row in assignments or []:
        key = (_iso_date(row.get("date")), _text(row.get("shift")))
        if key not in mine:
            continue
        name = _text(row.get("employee"))
        if name and name != employee:
            grouped.setdefault(key, []).append(name)
    return [
        {"date": key[0], "shift": key[1], "with": sorted(grouped[key])}
        for key in sorted(grouped)
    ]


def _mark_unseen(rows: List[dict], acknowledged_at: Any) -> List[dict]:
    """Flag the log rows that landed after the employee last acknowledged.

    A NULL `acknowledged_at` marks **everything** new rather than nothing: a
    person who has never opened the screen has by definition not seen the
    moves that concern them, and the opposite default would swallow exactly
    the first notification worth sending.

    Compared as `datetime`s, never as text -- both sides come from Postgres
    as aware timestamps, and string comparison would quietly do the wrong
    thing across a timezone or a differing microsecond precision.
    """
    marked = []
    for row in rows:
        created = row.get("created_at")
        is_new = True
        if acknowledged_at is not None and created is not None:
            try:
                is_new = created > acknowledged_at
            except TypeError:
                # Mixed aware/naive timestamps: treat as new rather than
                # dropping the notification on an error nobody would see.
                is_new = True
        entry = dict(row)
        entry["is_new"] = is_new
        marked.append(entry)
    return marked


def _names(row: dict, employee: str) -> bool:
    return employee in (
        _text(row.get("employee")), _text(row.get("replaced_employee"))
    )


def _window(schedule: Optional[dict]) -> tuple:
    if not schedule:
        return (None, None)
    return (
        _iso_date(schedule.get("starts_on")) or None,
        _iso_date(schedule.get("ends_on")) or None,
    )


def _iso_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value)[:10]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["EmployeeService"]
