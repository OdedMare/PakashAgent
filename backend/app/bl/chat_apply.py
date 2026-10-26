"""Apply a manager-approved chat plan atomically."""

import logging

from app.bl.chat_constraints import affected_periods
from app.bl.chat_contract import exception_warnings, fingerprint
from app.bl.chat_lifecycle import future_schedules
from app.bl.chat_management import apply_management, management_state
from app.bl.profile_service import ProfileService
from app.bl.schedule_service.operations import OperationApplier
from app.bl.shared import iso
from app.common.errors import AgentError, ConflictError

_log = logging.getLogger("pakash.chat")


class ChatPlanApplier:
    def __init__(self, repository, schedules, context, profiles=None):
        self._repo = repository
        self._schedules = schedules
        self._context = context
        self._profiles = profiles or ProfileService(repository)

    def apply(
        self, team_id, manager_id, chat_id, message_id,
        accept_exceptions=False, confirmation=None,
    ):
        before = None
        with self._repo.chat_approval(team_id, manager_id, chat_id, message_id) as message:
            if message["status"] == "applied":
                return self._repo.get_chat(team_id, manager_id, chat_id)
            payload = message["payload"]
            plan = payload.get("plan") or {}
            self._validate(team_id, plan, accept_exceptions)
            if plan.get("kind") == "profile":
                before = self._repo.team_profile(team_id)
            reason, agent_reason = self._reasons(plan, message["content"])
            schedule_id = self._apply_plan(team_id, plan, reason, agent_reason)
            self._repo.append_change(
                team_id, "chat_approved", schedule_id=schedule_id or None,
                reason=reason, agent_reason=agent_reason,
            )
            payload["receipt"] = {
                "schedule_id": schedule_id,
                "starts_on": plan.get("starts_on") or "",
                "message": self._receipt(plan),
            }
            self._repo.mark_chat_applied(chat_id, message_id, payload)
            if confirmation:
                self._repo.record_chat_confirmation(
                    chat_id, confirmation["content"], confirmation["request_id"],
                    payload["receipt"],
                )
        if before is not None:
            self._absorb(team_id, before)
        return self._repo.get_chat(team_id, manager_id, chat_id)

    def _absorb(self, team_id, before):
        """After the profile is committed: a new soldier or shift is fit into
        the drafts ahead of today. The approval already stands either way."""
        absorb = getattr(self._schedules, "absorb_profile_change", None)
        if absorb is None:
            return
        try:
            absorb(team_id, before, self._repo.team_profile(team_id))
        except Exception:
            _log.exception("absorbing a profile change failed")

    def _validate(self, team_id, plan, accept_exceptions):
        state = self._context.snapshot(team_id, plan.get("schedule_id") or "")
        if plan.get("kind") == "retire":
            state["future_schedules"] = future_schedules(
                self._repo, team_id, plan["effective_date"],
            )
        if plan.get("kind") == "manage":
            state["management"] = management_state(
                self._repo, team_id, plan["management_operations"],
            )
        elif plan.get("constraints"):
            state["constraint_periods"] = affected_periods(
                self._repo, team_id, plan["constraints"],
            )
        if fingerprint(state) != plan.get("snapshot"):
            raise ConflictError(
                "הסידור או כללי הצוות השתנו מאז ההמלצה. בקשו תוכנית מעודכנת"
            )
        if (exception_warnings(plan) or plan.get("exceptions")) and not accept_exceptions:
            raise ConflictError("יש לאשר במפורש את החריגות המוצגות בתוכנית")

    @staticmethod
    def _reasons(plan, message):
        reason = plan.get("reason") or message
        agent_reason = plan.get("agent_reason") or "שינוי שאושר בשיחה"
        conflicts = [row.get("message", "") for row in plan.get("warnings") or []]
        conflicts += plan.get("exceptions") or []
        if conflicts:
            agent_reason += "\nחריגות שאושרו במפורש: " + "; ".join(conflicts)
        return reason, agent_reason

    def _apply_plan(self, team_id, plan, reason, agent_reason):
        kind = plan.get("kind")
        schedule_id = plan.get("schedule_id") or ""
        for period_id in plan.get("draft_schedule_ids") or []:
            self._repo.set_schedule_status(period_id, team_id, "draft")
        if kind == "manage":
            apply_management(self._repo, self._schedules, team_id, plan["management_operations"])
        elif kind == "blank":
            schedule_id = self._schedules.create_blank(
                team_id, plan["starts_on"], plan["ends_on"],
            )["id"]
        elif kind == "delete_period":
            self._schedules.delete(schedule_id, team_id)
            schedule_id = ""
        elif kind == "retire":
            self._retire(team_id, plan, reason, agent_reason)
        elif kind == "restructure":
            self._restructure(team_id, schedule_id, plan, agent_reason)
        elif kind == "profile":
            self._profiles.update(team_id, **plan["profile_patch"])
        elif kind == "generate":
            schedule_id = self._commit_generation(team_id, plan, agent_reason)
        elif kind == "publish":
            self._schedules.publish(schedule_id, team_id)
        elif kind == "unpublish":
            self._schedules.unpublish(schedule_id, team_id)
        elif kind in ("changes", "clear"):
            self._apply_operations(team_id, schedule_id, plan, reason, agent_reason)
        else:
            raise AgentError("אין תוכנית להחיל")
        return schedule_id

    def _retire(self, team_id, plan, reason, agent_reason):
        applier = OperationApplier(self._repo)
        for period in plan["affected_schedules"]:
            for operation in period["operations"]:
                schedule = self._repo.get_schedule(period["schedule_id"], team_id)
                if not applier.apply(team_id, schedule, operation, reason, agent_reason):
                    raise ConflictError("לא ניתן לפנות את כל המשמרות. לא בוצע שינוי")
        self._repo.update_team_profile(team_id, plan["updated_profile"])

    def _restructure(self, team_id, schedule_id, plan, agent_reason):
        schedule = self._repo.get_schedule(schedule_id, team_id)
        for row in schedule["assignments"]:
            if plan["starts_on"] <= iso(row["date"]) <= plan["ends_on"]:
                self._repo.remove_assignment(row["id"], team_id)
        self._repo.replace_span_slots(
            schedule_id, team_id, plan["starts_on"], plan["ends_on"],
            plan["generated"]["slots"],
        )
        self._repo.update_team_profile(team_id, plan["updated_profile"])
        refreshed = self._repo.get_schedule(schedule_id, team_id)
        slots = {
            (row["shift_name"], iso(row["slot_date"])): row["id"]
            for row in refreshed["slots"]
        }
        for row in plan["generated"]["assignments"]:
            self._repo.add_assignment(
                schedule_id, team_id, slots[(row["shift"], iso(row["date"]))],
                row["employee"], row.get("reason") or agent_reason,
                source=row.get("source") or "agent",
            )

    def _apply_operations(self, team_id, schedule_id, plan, reason, agent_reason):
        applier = OperationApplier(self._repo)
        for operation in plan["operations"]:
            schedule = self._repo.get_schedule(schedule_id, team_id)
            if not applier.apply(team_id, schedule, operation, reason, agent_reason):
                raise ConflictError("לא ניתן להחיל את כל התוכנית. לא בוצע שינוי")
        for row in plan["constraints"]:
            if row.get("action") == "remove":
                self._repo.delete_availability(row["id"], team_id)
            else:
                self._repo.set_availability(
                    team_id, row["employee"], row["date"],
                    shift_name=row.get("shift") or "",
                    available=row.get("available", False),
                    reason=row.get("reason") or reason,
                    start_time=row.get("start_time") or "",
                    end_time=row.get("end_time") or "",
                    is_hard=row.get("is_hard", True), source="agent",
                )

    def _commit_generation(self, team_id, plan, agent_reason):
        generated = plan["generated"]
        schedule_id = plan["schedule_id"]
        if not schedule_id:
            schedule = self._repo.create_schedule(
                team_id, plan.get("period_starts_on") or plan["starts_on"],
                plan.get("period_ends_on") or plan["ends_on"],
            )
            schedule_id = schedule["id"]
            self._repo.replace_slots(
                schedule_id, team_id,
                plan.get("creation_slots") or generated["slots"],
            )
        schedule = self._repo.get_schedule(schedule_id, team_id)
        slots = {
            (row["shift_name"], iso(row["slot_date"])): row["id"]
            for row in schedule["slots"]
        }
        desired = {
            (row["employee"], row["shift"], iso(row["date"])): row
            for row in generated["assignments"]
        }
        first, last = plan["starts_on"], plan["ends_on"]
        existing = {
            (row["employee"], row["shift"], iso(row["date"])): row
            for row in schedule["assignments"]
            if first <= iso(row["date"]) <= last
        }
        for key, row in existing.items():
            if key not in desired:
                self._repo.remove_assignment(row["id"], team_id)
        for key, row in desired.items():
            if key not in existing:
                self._repo.add_assignment(
                    schedule_id, team_id, slots[(key[1], key[2])], key[0],
                    row.get("reason") or agent_reason,
                )
        return schedule_id

    @staticmethod
    def _receipt(plan):
        kind = plan.get("kind")
        receipt = "התוכנית הוחלה בהצלחה"
        if kind == "manage":
            receipt = "%d פעולות ניהול בוצעו ונשמרו בהצלחה" % len(plan["management_operations"])
        elif kind == "blank":
            receipt = "נפתח סידור ריק לשיבוץ ידני"
        elif kind == "delete_period":
            receipt = "הסידור נמחק. היסטוריית השינויים נשמרה"
        elif plan.get("constraints"):
            receipt += ". %d אילוצים עודכנו; ההשפעה על השיבוץ מוצגת בתוכנית." % len(plan["constraints"])
        if plan.get("draft_schedule_ids"):
            receipt = "הסידור הוחזר לטיוטה והתוכנית הוחלה בהצלחה"
        if kind == "retire":
            return "%s הוצא/ה מהסגל הפעיל. פונו %d משמרות עתידיות; ההיסטוריה נשמרה." % (
                plan["employee"], len(plan["operations"]),
            )
        if plan.get("coverage") and not plan["coverage"]["complete"]:
            receipt += ". נותרו %d משמרות שדורשות טיפול." % sum(
                not row["complete"] for row in plan["coverage"]["slots"]
            )
        return receipt
