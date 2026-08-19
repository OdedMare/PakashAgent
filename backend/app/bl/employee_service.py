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


    # -- swap requests -----------------------------------------------------

    def propose_swap(
        self,
        team_id: str,
        employee: str,
        assignment_id: str,
        counterparty: str,
        counterparty_assignment_id: str,
        reason: str = "",
    ) -> dict:
        """Offer a swap to a colleague. Moves nothing.

        Both shifts are named by *assignment id* rather than by date and
        shift: the employee picks two cells off a grid they are already
        looking at, and resolving ids here means a swap can never name a
        shift that is not really on the schedule. Both are then verified to
        belong to the people they are claimed for -- otherwise a requester
        could offer away a shift that was never theirs.

        Read from the published schedule only, which is the same one the
        personal area renders. Offering to swap a draft shift would be
        trading something the manager has not committed to yet.
        """
        schedule = self._schedules.current(team_id, role="member")
        if not schedule:
            raise AgentError("אין סידור מפורסם להחליף בו משמרות")
        mine = _assignment(schedule, assignment_id)
        theirs = _assignment(schedule, counterparty_assignment_id)
        if mine is None or theirs is None:
            raise AgentError("אחת המשמרות לא נמצאה בסידור")
        if _text(mine.get("employee")) != employee:
            raise AuthError("אפשר להציע רק משמרת שלך")
        if _text(theirs.get("employee")) != (counterparty or "").strip():
            raise AgentError("המשמרת שנבחרה אינה של העובד שנבחר")
        return self._repository.submit_swap(
            team_id,
            schedule["id"],
            employee,
            _iso_date(mine.get("date")),
            _text(mine.get("shift")),
            _text(theirs.get("employee")),
            _iso_date(theirs.get("date")),
            _text(theirs.get("shift")),
            reason=(reason or "").strip(),
        )

    def answer_swap(
        self, team_id: str, employee: str, swap_id: str, agreed: bool
    ) -> dict:
        """The colleague accepting or declining. Still moves nothing.

        Accepting is consent, not approval: it moves the swap into the
        manager's inbox and no further. Two employees agreeing between
        themselves does not change a schedule -- D14 gave employees exactly
        one write and this is still it, widened from "a constraint request"
        to "a request", with the manager as sole decider either way.
        """
        return self._repository.answer_swap(
            swap_id, team_id, employee, agreed
        )

    def withdraw_swap(
        self, team_id: str, employee: str, swap_id: str
    ) -> dict:
        return self._repository.withdraw_swap(swap_id, team_id, employee)

    def my_swaps(self, team_id: str, employee: str) -> List[dict]:
        """Every swap naming this person, on either side.

        Both sides read the same rows: the requester needs to see whether
        their offer was taken up, and the counterparty needs to see what they
        are being asked. `_mark_side` labels which of the two the caller is,
        so the screen does not have to compare names to know whether to show
        an accept button.
        """
        rows = self._repository.list_swaps(team_id, employee=employee)
        return [_mark_side(row, employee) for row in rows]

    def incoming_swaps(self, team_id: str, employee: str) -> List[dict]:
        """Offers waiting on this employee's answer -- their badge."""
        return [
            _mark_side(row, employee)
            for row in self._repository.list_swaps(
                team_id, employee=employee, status=STATUS_AWAITING
            )
            if _text(row.get("counterparty")) == employee
        ]

    # -- the manager's side ------------------------------------------------

    def pending_swaps(self, team_id: str) -> List[dict]:
        """Swaps both employees agreed to, awaiting the manager."""
        return self._repository.list_swaps(team_id, status=STATUS_PENDING)

    def all_swaps(self, team_id: str) -> List[dict]:
        return self._repository.list_swaps(team_id)

    def approve_swap(
        self, team_id: str, swap_id: str, decided_reason: str = ""
    ) -> dict:
        """Approve a swap and perform it.

        The ruling first, then the swap itself through
        `schedule_service.apply` -- the *same* `OP_SWAP` path a manager-typed
        swap takes. Reusing it is the point: a swap that arrived through the
        employee inbox and one the manager asked the agent for produce the
        same assignments and the same `ACTION_SWAPPED` log row, so the
        history reads as one kind of event rather than two.

        The manager's reason is required, exactly as D8 requires it of every
        other change. `agent_reason` records that the swap came from the
        employees rather than from the agent's judgment -- nobody's judgment
        was involved, and claiming otherwise in the log would be a
        justification the agent never made.
        """
        if not (decided_reason or "").strip():
            raise AgentError("צריך לציין סיבה לאישור ההחלפה")
        swap = self._repository.decide_swap(
            swap_id, team_id, STATUS_APPROVED, decided_reason.strip()
        )
        schedule = self._schedules.apply(
            team_id,
            swap["schedule_id"],
            [{
                "action": "swap",
                "employee": swap["requester"],
                "shift": swap.get("requester_shift") or "",
                "date": _iso_date(swap["requester_date"]),
                "with_employee": swap["counterparty"],
                "with_shift": swap.get("counterparty_shift") or "",
                "with_date": _iso_date(swap["counterparty_date"]),
            }],
            decided_reason.strip(),
            agent_reason=_swap_note(swap),
        )
        return {"swap": swap, "schedule": schedule}

    def reject_swap(
        self, team_id: str, swap_id: str, decided_reason: str = ""
    ) -> dict:
        """Refuse a swap, with a reason both employees will read.

        Required for the reason a constraint rejection requires one: two
        people arranged this between themselves, and a refusal that says
        nothing is how they stop using the feature and go back to arranging
        swaps the schedule never hears about.
        """
        if not (decided_reason or "").strip():
            raise AgentError("צריך לציין סיבה לדחייה")
        swap = self._repository.decide_swap(
            swap_id, team_id, STATUS_REJECTED, decided_reason.strip()
        )
        self._repository.append_change(
            team_id, ACTION_SWAP_REJECTED,
            schedule_id=swap.get("schedule_id"),
            employee=swap["requester"],
            replaced_employee=swap["counterparty"],
            slot_date=_iso_date(swap["requester_date"]),
            shift_name=swap.get("requester_shift") or "",
            reason=decided_reason.strip(),
            agent_reason="בקשת החלפה נדחתה",
        )
        return {"swap": swap}


def _assignment(schedule: dict, assignment_id: str) -> Optional[dict]:
    for row in (schedule or {}).get("assignments") or []:
        if row.get("id") == assignment_id:
            return row
    return None


def _mark_side(row: dict, employee: str) -> dict:
    """Label which side of the swap the reader is on.

    One row serves two people with different questions -- "did they accept?"
    and "do I accept?" -- and deciding that in the client would mean
    comparing names in three components instead of once here.
    """
    entry = dict(row)
    entry["is_requester"] = _text(row.get("requester")) == employee
    entry["is_counterparty"] = _text(row.get("counterparty")) == employee
    return entry


def _swap_note(swap: dict) -> str:
    """What the change log records as the agent's half of the reason.

    A swap the employees arranged had no agent judgment behind it, so this
    states the provenance rather than inventing a justification -- the same
    reasoning `assignments.source` encodes for a hand-placed row (D18).
    """
    requester = swap.get("requester") or ""
    counterparty = swap.get("counterparty") or ""
    note = "החלפה שסוכמה בין {} ל{} ואושרה על ידי המנהל".format(
        requester, counterparty
    )
    reason = (swap.get("reason") or "").strip()
    return "{}. הסיבה שנמסרה: {}".format(note, reason) if reason else note


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
