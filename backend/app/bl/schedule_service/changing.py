"""Changing a schedule the conversational way: propose, then apply (D8/D12)."""

from typing import List, Optional

from app.bl.schedule_service.constants import ACTION_MOVED, RECENT_CHANGES
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.operations import (
    OperationApplier,
    moved_from,
    nothing_applied,
    preview,
)
from app.bl.schedule_service.rows import find_assignment
from app.common.errors import AgentError, NotFoundError


class ChangeService:
    def __init__(self, context: ScheduleContext, change_agent, profiles):
        self._context = context
        self._repository = context.repository
        self._changes = change_agent
        self._profiles = profiles
        self._applier = OperationApplier(context.repository)

    def propose(
        self,
        team_id: str,
        request: str,
        schedule_id: Optional[str] = None,
        stated_reason: str = "",
        pending_request: str = "",
    ) -> dict:
        """What the agent would do about a request. Writes nothing.

        Returned with the warnings the change *would* produce, audited
        against the schedule as the proposal would leave it, so a proposal
        that breaks something is visible before it is accepted.
        """
        schedule = self._context.schedule_or_current(team_id, schedule_id) or {}
        proposal = self._changes.propose(
            self._context.profile(team_id),
            schedule,
            request,
            stated_reason=stated_reason,
            availability=self._context.availability(team_id, schedule),
            history=self._repository.change_log(team_id, limit=RECENT_CHANGES),
            pending_request=pending_request,
        )
        proposal["schedule_id"] = schedule.get("id", "")
        proposal["warnings"] = self._context.audit_rows(
            team_id, preview(schedule, proposal["operations"]), schedule,
        ) if schedule else []
        return proposal

    def apply(
        self,
        team_id: str,
        schedule_id: str,
        operations: List[dict],
        reason: str,
        agent_reason: str = "",
        profile_operations: Optional[List[dict]] = None,
    ) -> dict:
        """Apply a proposal the manager confirmed, and log it.

        The manager's reason is required here rather than merely requested:
        by this point they have been asked, and a change landing in the
        append-only log without one is a hole in the only history there is
        (D8).
        """
        profile_operations = profile_operations or []
        if operations and not (reason or "").strip():
            raise AgentError("צריך לציין סיבה לשינוי")
        if operations and profile_operations:
            raise AgentError("יש לאשר שינויי צוות ושינויי סידור בנפרד")
        if profile_operations:
            return self._apply_to_profile(team_id, profile_operations)
        schedule = self._repository.get_schedule(schedule_id, team_id)
        applied = sum(
            self._applier.apply(team_id, schedule, operation, reason, agent_reason)
            for operation in operations or []
        )
        if not applied:
            # Which operation found nothing, rather than only that nothing
            # happened -- the difference between a dead end and something the
            # manager can correct.
            raise AgentError(nothing_applied(operations or []))
        return self._context.fresh_view(schedule_id, team_id)

    def move(
        self,
        team_id: str,
        assignment_id: str,
        shift_name: str,
        slot_date: str,
        reason: str,
        agent_reason: str = "",
        schedule_id: Optional[str] = None,
    ) -> dict:
        """Move one assignment — what a confirmed drag resolves to.

        It arrives here only after the manager supplied a reason in the
        confirmation dialog, so a dragged shift carries exactly what a spoken
        one does (D8). `schedule_id` is the period the drag happened on;
        resolving it to "today's period" made a drag on any other week look
        for its slot in the wrong place.
        """
        if not (reason or "").strip():
            raise AgentError("צריך לציין סיבה להעברת המשמרת")
        schedule = self._context.require_schedule(team_id, schedule_id)
        slot = self._repository.find_slot(
            schedule["id"], team_id, shift_name, slot_date
        )
        if slot is None:
            raise NotFoundError("המשמרת לא נמצאה בסידור")
        previous = find_assignment(schedule, assignment_id)
        moved = self._repository.move_assignment(
            assignment_id, team_id, slot["id"], reason=agent_reason or reason,
        )
        self._repository.append_change(
            team_id, ACTION_MOVED, schedule_id=schedule["id"],
            employee=moved["employee"],
            slot_date=slot_date, shift_name=shift_name,
            reason=reason,
            agent_reason=agent_reason or moved_from(previous),
        )
        return self._context.fresh_view(schedule["id"], team_id)

    def _apply_to_profile(
        self, team_id: str, profile_operations: List[dict]
    ) -> dict:
        profile = self._profiles.apply_operations(team_id, profile_operations)
        schedule = self._repository.current_schedule(team_id)
        if schedule:
            return self._context.view(schedule, team_id)
        return {"status": "ok", "profile": profile}
