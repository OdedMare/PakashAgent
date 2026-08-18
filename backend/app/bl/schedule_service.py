"""Persistence and orchestration around the schedule.

`Scheduler` decides who works; `ChangeAgent` decides what a request means;
`audit` recomputes the countable facts. This decides what to remember and in
what order to do things — which is why it, and not they, owns the repository.

Two shapes are load-bearing here:

- **Propose and apply are separate calls.** A proposal writes nothing. The
  manager confirms in between, and only then does anything land
  ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)). A drag on
  the calendar goes through exactly the same two steps as a sentence typed at
  the agent — the gesture is a proposal, not an edit.
- **Every response carrying a schedule carries its warnings.** They are
  advisory and never gate anything
  ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)):
  a schedule with warnings is still a `200` and still renders.

Every method takes the team from the caller's signed session and passes it to
the repository, which filters on it. It is never taken from a request body.
"""

import datetime
from typing import Any, Dict, List, Optional

from app.bl.audit import audit
from app.bl.changes import ChangeAgent, OP_ASSIGN, OP_REMOVE, OP_SWAP
from app.bl.scheduler import Scheduler
from app.common.errors import AgentError, NotFoundError
from app.dal.repository.schedules import (
    SOURCE_AGENT,
    SOURCE_MANAGER,
    week_bounds,
)

# What the change log calls each kind of entry. Stored rather than derived so
# the history stays readable even as the code that wrote it changes.
ACTION_GENERATED = "generated"
ACTION_PUBLISHED = "published"
ACTION_MOVED = "moved"
ACTION_ASSIGNED = "assigned"
ACTION_REMOVED = "removed"
ACTION_SWAPPED = "swapped"
ACTION_CONSTRAINT = "constraint"


class ScheduleService:
    def __init__(self, repository, llm):
        self._repository = repository
        self._scheduler = Scheduler(llm)
        self._changes = ChangeAgent(llm)

    # -- reading -----------------------------------------------------------

    def current(self, team_id: str, role: str = "boss") -> Optional[dict]:
        """The period in play, audited, or None when there is none yet.

        A member sees only published schedules. A draft is the manager's
        working state, and publishing is the act that makes it the team's
        ([D5](../../../docs/DECISIONS.md#d5--employees-are-read-only)).
        """
        schedule = self._repository.current_schedule(
            team_id, published_only=(role != "boss")
        )
        if schedule is None:
            return None
        return self._view(schedule, team_id)

    def get(self, schedule_id: str, team_id: str) -> dict:
        return self._view(
            self._repository.get_schedule(schedule_id, team_id), team_id
        )

    def list_periods(self, team_id: str) -> List[dict]:
        return self._repository.list_schedules(team_id)

    def overview(self, team_id: str, role: str = "boss") -> dict:
        """Everything the management area opens with, in one call.

        The team, the roster, the shift vocabulary, the current period and
        its warnings, the constraints, and the recent history. One request
        rather than six because they are read together and a half-loaded
        management screen is worse than a slightly slower one.
        """
        profile = self._repository.team_profile(team_id) or {}
        schedule = self.current(team_id, role)
        window = _window(schedule)
        return {
            "profile": profile,
            "employees": _employees(profile),
            "shifts": _shifts(profile),
            "schedule": schedule,
            "periods": self._repository.list_schedules(team_id),
            "availability": self._repository.availability(
                team_id, window[0], window[1]
            ),
            "changes": self._repository.change_log(team_id, limit=40),
        }

    # -- generating --------------------------------------------------------

    def generate(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        instructions: str = "",
    ) -> dict:
        """Build a period and store it as a draft.

        The interview must have produced a profile first: without the shift
        vocabulary there is nothing to build a grid out of, and guessing one
        would be exactly the hardcoding D9 forbids.
        """
        profile = self._repository.team_profile(team_id)
        if not profile:
            raise AgentError(
                "צריך להשלים את ראיון ההיכרות לפני בניית סידור"
            )
        if not starts_on or not ends_on:
            starts_on, ends_on = week_bounds()

        result = self._scheduler.generate(
            profile,
            starts_on,
            ends_on,
            availability=self._repository.availability(
                team_id, starts_on, ends_on
            ),
            history=self._recent_assignments(team_id, starts_on),
            instructions=instructions,
        )

        schedule = self._repository.create_schedule(
            team_id, starts_on, ends_on
        )
        slots = self._repository.replace_slots(
            schedule["id"], team_id, result["slots"]
        )
        index = {
            (slot["shift_name"], _iso(slot["slot_date"])): slot["id"]
            for slot in slots
        }
        rows = []
        for item in result["assignments"]:
            slot_id = index.get((item["shift"], item["date"]))
            if slot_id is None:
                continue
            rows.append({
                "slot_id": slot_id,
                "employee": item["employee"],
                "reason": item["reason"],
            })
        self._repository.replace_assignments(schedule["id"], team_id, rows)
        self._repository.append_change(
            team_id, ACTION_GENERATED, schedule_id=schedule["id"],
            reason=instructions,
            agent_reason=result["summary"],
        )

        view = self._view(
            self._repository.get_schedule(schedule["id"], team_id), team_id
        )
        view["notes"] = result["notes"]
        view["summary"] = result["summary"]
        return view

    def publish(self, schedule_id: str, team_id: str) -> dict:
        """Make a draft the team's. Members read only published periods."""
        schedule = self._repository.set_schedule_status(
            schedule_id, team_id, "published"
        )
        self._repository.append_change(
            team_id, ACTION_PUBLISHED, schedule_id=schedule_id,
            agent_reason="הסידור פורסם לצוות",
        )
        return self._view(schedule, team_id)

    def unpublish(self, schedule_id: str, team_id: str) -> dict:
        return self._view(
            self._repository.set_schedule_status(
                schedule_id, team_id, "draft"
            ),
            team_id,
        )

    def delete(self, schedule_id: str, team_id: str) -> None:
        self._repository.delete_schedule(schedule_id, team_id)

    # -- changing ----------------------------------------------------------

    def propose(
        self,
        team_id: str,
        request: str,
        schedule_id: Optional[str] = None,
        stated_reason: str = "",
    ) -> dict:
        """What the agent would do about a request. Writes nothing.

        The manager confirms this before it lands. Returned with the warnings
        the change *would* produce, so a proposal that breaks something is
        visible before it is accepted rather than after.
        """
        schedule = self._require_schedule(team_id, schedule_id)
        profile = self._repository.team_profile(team_id) or {}
        window = _window(schedule)
        proposal = self._changes.propose(
            profile,
            schedule,
            request,
            stated_reason=stated_reason,
            availability=self._repository.availability(
                team_id, window[0], window[1]
            ),
            history=self._repository.change_log(team_id, limit=40),
        )
        proposal["schedule_id"] = schedule["id"]
        # The audit runs against the schedule as the proposal would leave it,
        # so the manager sees the consequence rather than the current state.
        proposal["warnings"] = self._audit_rows(
            team_id,
            _applied(schedule, proposal["operations"]),
            schedule,
        )
        return proposal

    def apply(
        self,
        team_id: str,
        schedule_id: str,
        operations: List[dict],
        reason: str,
        agent_reason: str = "",
    ) -> dict:
        """Apply a proposal the manager confirmed, and log it.

        The manager's reason is required here rather than merely requested:
        by this point they have been asked, and a change landing in the
        append-only log without one is a hole in the only history there is
        ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).
        """
        if not (reason or "").strip():
            raise AgentError("צריך לציין סיבה לשינוי")
        schedule = self._repository.get_schedule(schedule_id, team_id)
        applied = 0
        for operation in operations or []:
            applied += self._apply_one(
                team_id, schedule, operation, reason, agent_reason
            )
        if not applied:
            raise AgentError("לא היה שינוי להחיל")
        return self._view(
            self._repository.get_schedule(schedule_id, team_id), team_id
        )

    def move(
        self,
        team_id: str,
        assignment_id: str,
        shift_name: str,
        slot_date: str,
        reason: str,
        agent_reason: str = "",
    ) -> dict:
        """Move one assignment — what a confirmed drag resolves to.

        The gesture happens on the calendar, but it arrives here only after
        the manager has supplied a reason in the confirmation dialog, so a
        dragged shift carries exactly what a spoken one does: their reason
        and the agent's ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).
        Dragging is a way of *proposing* a change, not a way around the
        decision that changes are explained.
        """
        if not (reason or "").strip():
            raise AgentError("צריך לציין סיבה להעברת המשמרת")
        schedule = self._require_schedule(team_id, None)
        slot = self._repository.find_slot(
            schedule["id"], team_id, shift_name, slot_date
        )
        if slot is None:
            raise NotFoundError("המשמרת לא נמצאה בסידור")
        previous = _find_assignment(schedule, assignment_id)
        moved = self._repository.move_assignment(
            assignment_id, team_id, slot["id"],
            reason=agent_reason or reason,
        )
        self._repository.append_change(
            team_id, ACTION_MOVED, schedule_id=schedule["id"],
            employee=moved["employee"],
            slot_date=slot_date, shift_name=shift_name,
            reason=reason,
            agent_reason=agent_reason or _moved_from(previous),
        )
        return self._view(
            self._repository.get_schedule(schedule["id"], team_id), team_id
        )

    def _apply_one(
        self,
        team_id: str,
        schedule: dict,
        operation: dict,
        reason: str,
        agent_reason: str,
    ) -> int:
        """One operation against the stored schedule. Returns rows changed."""
        action = (operation or {}).get("action")
        employee = (operation.get("employee") or "").strip()
        shift = (operation.get("shift") or "").strip()
        date = _iso(operation.get("date"))
        if not action or not employee or not date:
            return 0
        own_reason = (operation.get("reason") or "").strip() or agent_reason

        if action == OP_REMOVE:
            existing = _match(schedule, employee, shift, date)
            if existing is None:
                return 0
            self._repository.remove_assignment(existing["id"], team_id)
            self._repository.append_change(
                team_id, ACTION_REMOVED, schedule_id=schedule["id"],
                employee=employee, slot_date=date, shift_name=shift,
                reason=reason, agent_reason=own_reason,
            )
            return 1

        if action == OP_ASSIGN:
            slot = self._repository.find_slot(
                schedule["id"], team_id, shift, date
            )
            if slot is None:
                return 0
            self._repository.add_assignment(
                schedule["id"], team_id, slot["id"], employee,
                own_reason or reason,
            )
            self._repository.append_change(
                team_id, ACTION_ASSIGNED, schedule_id=schedule["id"],
                employee=employee, slot_date=date, shift_name=shift,
                reason=reason, agent_reason=own_reason,
            )
            return 1

        if action == OP_SWAP:
            other = (operation.get("with_employee") or "").strip()
            other_shift = (operation.get("with_shift") or "").strip() or shift
            other_date = _iso(operation.get("with_date")) or date
            first = _match(schedule, employee, shift, date)
            second = _match(schedule, other, other_shift, other_date)
            if first is None or second is None:
                return 0
            self._repository.move_assignment(
                first["id"], team_id, second["slot_id"],
                reason=own_reason or reason,
            )
            self._repository.move_assignment(
                second["id"], team_id, first["slot_id"],
                reason=own_reason or reason,
            )
            self._repository.append_change(
                team_id, ACTION_SWAPPED, schedule_id=schedule["id"],
                employee=employee, replaced_employee=other,
                slot_date=date, shift_name=shift,
                reason=reason, agent_reason=own_reason,
            )
            return 1

        return 0

    # -- constraints -------------------------------------------------------

    def set_constraint(
        self,
        team_id: str,
        employee: str,
        constraint_date: str,
        shift_name: str = "",
        available: bool = False,
        reason: str = "",
        source: str = SOURCE_MANAGER,
    ) -> dict:
        """Record a constraint for an employee.

        Written by the manager or by the agent during a conversation, never
        by the employee — they have no account at all
        ([D10](../../../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)),
        so `source` records where the information came from rather than who
        typed it. `employee_reported` is the manager writing down what
        someone told them.
        """
        if not (employee or "").strip():
            raise AgentError("צריך לציין עובד")
        if not (constraint_date or "").strip():
            raise AgentError("צריך לציין תאריך")
        row = self._repository.set_availability(
            team_id, employee.strip(), constraint_date,
            shift_name=(shift_name or "").strip(),
            available=available, reason=(reason or "").strip(), source=source,
        )
        self._repository.append_change(
            team_id, ACTION_CONSTRAINT,
            employee=employee.strip(), slot_date=constraint_date,
            shift_name=(shift_name or "").strip(),
            reason=(reason or "").strip(),
            agent_reason="זמין" if available else "אילוץ נרשם",
        )
        return row

    def constraints(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        employee: Optional[str] = None,
    ) -> List[dict]:
        return self._repository.availability(
            team_id, starts_on, ends_on, employee
        )

    def delete_constraint(self, row_id: str, team_id: str) -> None:
        self._repository.delete_availability(row_id, team_id)

    def history(
        self, team_id: str, schedule_id: Optional[str] = None
    ) -> List[dict]:
        return self._repository.change_log(team_id, schedule_id)

    # -- helpers -----------------------------------------------------------

    def _view(self, schedule: dict, team_id: str) -> dict:
        """A schedule with its warnings attached.

        Warnings ride along on every response carrying a schedule, and a
        response with warnings is still a success — they are advisory
        ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
        """
        schedule = dict(schedule)
        schedule["warnings"] = self._audit_rows(
            team_id, schedule.get("assignments") or [], schedule
        )
        return schedule

    def _audit_rows(
        self, team_id: str, assignments: List[dict], schedule: dict
    ) -> List[dict]:
        profile = self._repository.team_profile(team_id) or {}
        window = _window(schedule)
        return audit(
            [
                {
                    "employee": row.get("employee"),
                    "shift": row.get("shift"),
                    "date": _iso(row.get("date")),
                }
                for row in assignments
            ],
            _shifts(profile),
            _employees(profile),
            availability=[
                {
                    "employee": row.get("employee"),
                    "date": _iso(row.get("constraint_date")),
                    "shift": row.get("shift_name") or "",
                    "available": row.get("available"),
                    "reason": row.get("reason") or "",
                }
                for row in self._repository.availability(
                    team_id, window[0], window[1]
                )
            ],
            profile=profile,
        )

    def _require_schedule(
        self, team_id: str, schedule_id: Optional[str]
    ) -> dict:
        if schedule_id:
            return self._repository.get_schedule(schedule_id, team_id)
        schedule = self._repository.current_schedule(team_id)
        if schedule is None:
            raise NotFoundError("אין סידור פעיל")
        return schedule

    def _recent_assignments(
        self, team_id: str, before: str
    ) -> List[dict]:
        """Assignments from earlier periods, for fairness.

        The scheduler needs to know who has been carrying the nights, and
        that is not visible inside the period being built.
        """
        rows: List[dict] = []
        for period in self._repository.list_schedules(team_id):
            if _iso(period["starts_on"]) >= before:
                continue
            rows.extend(
                {
                    "employee": row["employee"],
                    "shift": row["shift"],
                    "date": _iso(row["date"]),
                }
                for row in self._repository.assignments(period["id"], team_id)
            )
            if len(rows) > 300:
                break
        return rows


def _window(schedule: Optional[dict]) -> tuple:
    """The date range a schedule covers, as ISO strings."""
    if not schedule:
        return None, None
    return _iso(schedule.get("starts_on")), _iso(schedule.get("ends_on"))


def _employees(profile: dict) -> List[dict]:
    people = (profile or {}).get("employees")
    return [row for row in people or [] if isinstance(row, dict)]


def _shifts(profile: dict) -> List[dict]:
    shifts = (profile or {}).get("shifts")
    return [row for row in shifts or [] if isinstance(row, dict)]


def _match(
    schedule: dict, employee: str, shift: str, date: str
) -> Optional[dict]:
    """The stored assignment an operation names, if it is there."""
    for row in schedule.get("assignments") or []:
        if (
            row.get("employee") == employee
            and _iso(row.get("date")) == date
            and (not shift or row.get("shift") == shift)
        ):
            return row
    return None


def _find_assignment(schedule: dict, assignment_id: str) -> Optional[dict]:
    for row in schedule.get("assignments") or []:
        if row.get("id") == assignment_id:
            return row
    return None


def _moved_from(previous: Optional[dict]) -> str:
    """A default agent reason for a drag the manager did not annotate.

    Says what happened rather than pretending to a judgment the agent did not
    make — the manager moved this, and the log should read that way.
    """
    if not previous:
        return "הועבר על ידי המנהל"
    return "הועבר על ידי המנהל מ%s ב-%s" % (
        previous.get("shift") or "", _iso(previous.get("date")),
    )


def _applied(schedule: dict, operations: List[dict]) -> List[dict]:
    """The assignment list as a proposal would leave it.

    Computed in memory and never written: this exists so the audit can report
    on a change the manager has not accepted yet.
    """
    rows = [
        {
            "employee": row.get("employee"),
            "shift": row.get("shift"),
            "date": _iso(row.get("date")),
        }
        for row in schedule.get("assignments") or []
    ]
    for operation in operations or []:
        action = operation.get("action")
        employee = operation.get("employee")
        shift = operation.get("shift")
        date = _iso(operation.get("date"))
        if action == OP_REMOVE:
            rows = [
                row for row in rows
                if not (row["employee"] == employee
                        and row["date"] == date
                        and (not shift or row["shift"] == shift))
            ]
        elif action == OP_ASSIGN:
            rows.append(
                {"employee": employee, "shift": shift, "date": date}
            )
        elif action == OP_SWAP:
            other = operation.get("with_employee")
            other_shift = operation.get("with_shift") or shift
            other_date = _iso(operation.get("with_date")) or date
            for row in rows:
                if (row["employee"] == employee and row["date"] == date
                        and row["shift"] == shift):
                    row["employee"] = other
                elif (row["employee"] == other and row["date"] == other_date
                        and row["shift"] == other_shift):
                    row["employee"] = employee
    return rows


def _iso(value: Any) -> str:
    """Dates arrive as `datetime.date` from SQL and as strings from the model."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value.strip() if isinstance(value, str) else ""


__all__ = ["ScheduleService"]
