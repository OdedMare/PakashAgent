"""The durable copilot's deterministic observation and action boundary."""

import datetime
from typing import List, Optional

from app.common.errors import ConflictError
from app.dal.repository.copilot import (
    ACTION_FOLLOW_UP,
    ACTION_PROFILE_REVIEW,
    ACTION_SCHEDULE_REPAIR,
)

_PROFILE_REVIEW_DAYS = 90


class CopilotService:
    def __init__(self, repository, schedules, interviews):
        self._repository = repository
        self._schedules = schedules
        self._interviews = interviews

    def scan(self, team_id: str, job_id: Optional[str] = None) -> List[dict]:
        """Read one workspace and leave durable, deduplicated inbox items."""
        created = []
        profile = self._repository.team_profile(team_id) or {}
        updated_at = self._repository.latest_profile_updated_at(team_id)
        profile_stamp = updated_at.isoformat() if updated_at else "none"
        completeness = profile.get("completeness") or {}
        gaps = list(completeness.get("missing_topics") or [])
        gaps += list(completeness.get("open_points") or [])
        for gap in gaps:
            text = str(gap).strip()
            if not text:
                continue
            item = self._create(
                team_id, "follow-up:%s:%s" % (profile_stamp, _key(text)),
                ACTION_FOLLOW_UP,
                "נדרש להשלים מידע בראיון",
                text,
                {"question": text, "suggestion": text},
                job_id,
            )
            if item:
                created.append(item)

        if updated_at and _older_than(updated_at, _PROFILE_REVIEW_DAYS):
            stamp = updated_at.date().isoformat()
            question = (
                "עבר זמן מאז ראיון ההיכרות. האם העובדים, המשמרות והכללים "
                "עדיין מעודכנים?"
            )
            item = self._create(
                team_id, "profile-review:%s" % stamp, ACTION_PROFILE_REVIEW,
                "כדאי לרענן את פרטי מקום העבודה", question,
                {"question": question, "suggestion": question}, job_id,
            )
            if item:
                created.append(item)

        schedule = self._schedules.current(team_id)
        for warning in (schedule or {}).get("warnings") or []:
            fingerprint = "schedule:%s:%s:%s:%s:%s" % (
                schedule.get("id", ""), warning.get("code", "warning"),
                warning.get("employee", ""), warning.get("date", ""),
                warning.get("shift", ""),
            )
            message = warning.get("message") or "נמצאה בעיה בסידור"
            suggestion = "בדוק את הבעיה בסידור והצע תיקון: %s" % message
            item = self._create(
                team_id, fingerprint, ACTION_SCHEDULE_REPAIR,
                "נמצאה בעיה בסידור", message,
                {"suggestion": suggestion, "warning": warning,
                 "schedule_id": schedule.get("id")},
                job_id,
            )
            if item:
                created.append(item)
        return created

    def _create(
        self, team_id: str, fingerprint: str, action_type: str,
        title: str, detail: str, payload: dict, job_id: Optional[str],
    ) -> Optional[dict]:
        mode = self._repository.copilot_permission(team_id, action_type)
        item = self._repository.create_copilot_item(
            team_id, fingerprint, "observation" if mode == "observe" else "proposal",
            action_type, title, detail, payload, job_id,
        )
        # Automatic follow-up opens a resumable interview but never answers it.
        # Schedule repair remains a proposal because D8 requires the manager's
        # own reason before any assignment changes.
        if item and mode == "auto" and action_type in (
            ACTION_FOLLOW_UP, ACTION_PROFILE_REVIEW,
        ):
            return self.approve(item["id"], team_id, actor="system")
        return item

    def approve(
        self, item_id: str, team_id: str, actor: str = "manager"
    ) -> dict:
        item = self._repository.copilot_item(item_id, team_id)
        if item["status"] not in ("pending", "rolled_back"):
            raise ConflictError("הפעולה כבר טופלה")
        if item["kind"] == "observation":
            raise ConflictError("תצפית אינה פעולה שניתן לאשר")
        before = {"status": item["status"]}
        if item["action_type"] in (ACTION_FOLLOW_UP, ACTION_PROFILE_REVIEW):
            question = (item.get("payload") or {}).get("question") or item["detail"]
            turn = self._interviews.start_follow_up(team_id, question)
            after = {"session_id": turn["session_id"]}
            verification = {
                "ok": True, "check": "active_interview_created",
                "session_id": turn["session_id"],
            }
            return self._repository.transition_copilot_item(
                item_id, team_id, "applied", before, after, verification,
                actor=actor,
            )
        verification = {
            "ok": True, "check": "proposal_ready_for_manager",
        }
        return self._repository.transition_copilot_item(
            item_id, team_id, "approved", before, {}, verification,
            actor=actor,
        )

    def dismiss(self, item_id: str, team_id: str) -> dict:
        item = self._repository.copilot_item(item_id, team_id)
        if item["status"] not in ("pending", "approved"):
            raise ConflictError("הפעולה כבר טופלה")
        return self._repository.transition_copilot_item(
            item_id, team_id, "dismissed",
            {"status": item["status"]}, {}, {"ok": True},
        )

    def rollback(self, item_id: str, team_id: str) -> dict:
        item = self._repository.copilot_item(item_id, team_id)
        if item["status"] not in ("approved", "applied", "dismissed"):
            raise ConflictError("אין לפעולה הזאת שינוי שניתן לבטל")
        after_state = item.get("after_state") or {}
        session_id = after_state.get("session_id")
        if session_id:
            self._repository.discard_follow_up(session_id, team_id)
        return self._repository.transition_copilot_item(
            item_id, team_id, "rolled_back",
            {"status": item["status"], **after_state}, {},
            {"ok": True, "check": "side_effect_removed"},
        )


def _key(value: str) -> str:
    return "-".join(value.lower().split())[:180]


def _older_than(value, days: int) -> bool:
    now = datetime.datetime.now(value.tzinfo) if value.tzinfo else datetime.datetime.now()
    return value < now - datetime.timedelta(days=days)


__all__ = ["CopilotService"]
