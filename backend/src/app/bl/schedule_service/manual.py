"""The manual path (D18): placing, removing, clearing, publishing by hand.

No model call anywhere in this file. These are the only schedule writes that
land immediately, and every one of them still leaves a reasoned row in the
change log.
"""

from typing import Optional

from app.bl.schedule_service.constants import (
    ACTION_ASSIGNED,
    ACTION_PUBLISHED,
    ACTION_REMOVED,
    MANUAL_REASON,
)
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.rows import find_assignment, iso
from app.common.errors.errors import AgentError, NotFoundError
from app.dal.repository.schedules import ASSIGNED_BY_MANAGER


class ManualEditor:
    def __init__(self, context: ScheduleContext):
        self._context = context
        self._repository = context.repository

    def assign(
        self,
        team_id: str,
        shift_name: str,
        slot_date: str,
        employee: str,
        reason: str = "",
        schedule_id: Optional[str] = None,
    ) -> dict:
        """Place one person on one slot, by hand.

        Writes immediately rather than proposing. Not a reversal of D12: a
        drag *moves someone who is already placed*, while filling an empty
        cell takes nothing away from anybody. `reason` is the manager's own
        sentence when they gave one; otherwise the row carries a true
        statement of where it came from.
        """
        employee = (employee or "").strip()
        if not employee:
            raise AgentError("צריך לבחור עובד לשיבוץ")
        schedule = self._context.require_schedule(team_id, schedule_id)
        slot = self._repository.find_slot(
            schedule["id"], team_id, shift_name, slot_date
        )
        if slot is None:
            raise NotFoundError("המשמרת לא נמצאה בסידור")
        person = next((row for row in self._context.profile(team_id).get("employees") or []
                       if row.get("name") == employee), {})
        if person.get("inactive_from") and slot_date >= person["inactive_from"]:
            raise AgentError("העובד סיים את העבודה לפני המשמרת שנבחרה. יש לבחור עובד פעיל")
        stated = (reason or "").strip()
        row = self._repository.add_assignment(
            schedule["id"], team_id, slot["id"], employee,
            stated or MANUAL_REASON,
            source=ASSIGNED_BY_MANAGER,
        )
        self._repository.append_change(
            team_id, ACTION_ASSIGNED, schedule_id=schedule["id"],
            employee=employee, slot_date=slot_date, shift_name=shift_name,
            reason=stated, agent_reason=MANUAL_REASON,
        )
        view = self._context.fresh_view(schedule["id"], team_id)
        # `add_assignment` conflicts silently on (slot, employee), so a double
        # click returns the row that was already there. Saying so lets the UI
        # stay quiet instead of reporting a change it did not make.
        view["assigned"] = (row or {}).get("id", "")
        return view

    def unassign(
        self,
        team_id: str,
        assignment_id: str,
        reason: str = "",
        schedule_id: Optional[str] = None,
    ) -> dict:
        """Take one person off a slot, by hand.

        Removing somebody *does* take a shift away from a person, so the
        manager's reason is recorded when given. It is not enforced: a cell
        cleared seconds after being filled by mistake is a correction rather
        than a decision.
        """
        schedule = self._context.require_schedule(team_id, schedule_id)
        existing = find_assignment(schedule, assignment_id)
        if existing is None:
            raise NotFoundError("השיבוץ לא נמצא")
        self._remove(
            team_id, schedule["id"], existing, (reason or "").strip(),
            MANUAL_REASON,
        )
        return self._context.fresh_view(schedule["id"], team_id)

    def clear(
        self,
        team_id: str,
        schedule_id: str,
        slot_date: str = "",
        reason: str = "",
    ) -> dict:
        """Empty a day's shifts, or the whole period's. **Keeps the grid.**

        The slots are the shape of the week and come from the vocabulary, so
        clearing them too would leave a period that renders as no shifts at
        all rather than as unstaffed ones. Every removed row is logged
        individually: a day cleared in one gesture is still N people taken
        off N shifts, and the log is the only history there is (D4).
        """
        schedule = self._context.require_schedule(team_id, schedule_id)
        wanted = iso(slot_date)
        rows = [
            row for row in schedule.get("assignments") or []
            if not wanted or iso(row.get("date")) == wanted
        ]
        agent_reason = (
            "נמחק בניקוי היום על ידי המנהל" if wanted
            else "נמחק בניקוי הסידור על ידי המנהל"
        )
        stated = (reason or "").strip()
        for row in rows:
            self._remove(team_id, schedule["id"], row, stated, agent_reason)
        view = self._context.fresh_view(schedule["id"], team_id)
        # How many rows actually went, so the UI can say "nothing to clear"
        # rather than report a change it did not make.
        view["cleared"] = len(rows)
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
        return self._context.view(schedule, team_id)

    def unpublish(self, schedule_id: str, team_id: str) -> dict:
        return self._context.view(
            self._repository.set_schedule_status(schedule_id, team_id, "draft"),
            team_id,
        )

    def delete(self, schedule_id: str, team_id: str) -> None:
        self._repository.delete_schedule(schedule_id, team_id)

    def _remove(
        self,
        team_id: str,
        schedule_id: str,
        row: dict,
        reason: str,
        agent_reason: str,
    ) -> None:
        self._repository.remove_assignment(row["id"], team_id)
        self._repository.append_change(
            team_id, ACTION_REMOVED, schedule_id=schedule_id,
            employee=row.get("employee") or "",
            slot_date=iso(row.get("date")),
            shift_name=row.get("shift") or "",
            reason=reason,
            agent_reason=agent_reason,
        )
