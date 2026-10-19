"""Durable copilot observation and action boundary."""

import datetime
from typing import List, Optional

from app.common.errors import ConflictError
from app.dal.repository.copilot import (
    ACTION_PROFILE_REVIEW,
    ACTION_SCHEDULE_REPAIR,
)

_PROFILE_REVIEW_DAYS = 90


class CopilotService:
    def __init__(self, repository, schedules):
        self._repository = repository
        self._schedules = schedules

    def scan(self, team_id: str, job_id: Optional[str] = None) -> List[dict]:
        """Read one workspace and leave durable, deduplicated inbox items.

        Three observers -- what the profile still lacks, whether the profile
        has gone stale, and what the current schedule warns about. Each item
        is keyed by a fingerprint, so a rescan never duplicates one.
        """
        found = (
            self._profile_gaps(team_id, job_id)
            + self._stale_profile(team_id, job_id)
            + self._schedule_warnings(team_id, job_id)
        )
        return [item for item in found if item]

    def _profile_gaps(self, team_id: str, job_id: Optional[str]) -> List[Optional[dict]]:
        profile = self._repository.team_profile(team_id) or {}
        updated_at = self._repository.latest_profile_updated_at(team_id)
        stamp = updated_at.isoformat() if updated_at else "none"
        completeness = profile.get("completeness") or {}
        gaps = list(completeness.get("missing_topics") or [])
        gaps += list(completeness.get("open_points") or [])
        texts = [str(gap).strip() for gap in gaps if str(gap).strip()]
        return [
            self._create(
                team_id, "profile-gap:%s:%s" % (stamp, _key(text)), ACTION_PROFILE_REVIEW,
                "נדרש להשלים מידע בפרופיל", text,
                {"question": text, "suggestion": text}, job_id,
            )
            for text in texts
        ]

    def _stale_profile(self, team_id: str, job_id: Optional[str]) -> List[Optional[dict]]:
        updated_at = self._repository.latest_profile_updated_at(team_id)
        if not updated_at or not _older_than(updated_at, _PROFILE_REVIEW_DAYS):
            return []
        question = (
            "עבר זמן מאז עדכון הפרופיל. האם העובדים, המשמרות והכללים "
            "עדיין מעודכנים?"
        )
        return [self._create(
            team_id, "profile-review:%s" % updated_at.date().isoformat(),
            ACTION_PROFILE_REVIEW, "כדאי לרענן את פרטי מקום העבודה", question,
            {"question": question, "suggestion": question}, job_id,
        )]

    def _schedule_warnings(self, team_id: str, job_id: Optional[str]) -> List[Optional[dict]]:
        schedule = self._schedules.current(team_id) or {}
        items = []
        for warning in schedule.get("warnings") or []:
            fingerprint = "schedule:%s:%s:%s:%s:%s" % (
                schedule.get("id", ""), warning.get("code", "warning"),
                warning.get("employee", ""), warning.get("date", ""),
                warning.get("shift", ""),
            )
            message = warning.get("message") or "נמצאה בעיה בסידור"
            items.append(self._create(
                team_id, fingerprint, ACTION_SCHEDULE_REPAIR,
                "נמצאה בעיה בסידור", message,
                {"suggestion": "בדוק את הבעיה בסידור והצע תיקון: %s" % message,
                 "warning": warning, "schedule_id": schedule.get("id")},
                job_id,
            ))
        return items

    def _create(
        self, team_id: str, fingerprint: str, action_type: str,
        title: str, detail: str, payload: dict, job_id: Optional[str],
    ) -> Optional[dict]:
        mode = self._repository.copilot_permission(team_id, action_type)
        item = self._repository.create_copilot_item(
            team_id, fingerprint, "observation" if mode == "observe" else "proposal",
            action_type, title, detail, payload, job_id,
        )
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
        if item["action_type"] == ACTION_PROFILE_REVIEW:
            return self._repository.transition_copilot_item(
                item_id, team_id, "approved", before, {},
                {"ok": True, "check": "profile_edit_requested"},
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
        return self._repository.transition_copilot_item(
            item_id, team_id, "rolled_back",
            {"status": item["status"]}, {},
            {"ok": True, "check": "no_side_effect"},
        )


def _key(value: str) -> str:
    return "-".join(value.lower().split())[:180]


def _older_than(value, days: int) -> bool:
    now = datetime.datetime.now(value.tzinfo) if value.tzinfo else datetime.datetime.now()
    return value < now - datetime.timedelta(days=days)


__all__ = ["CopilotService"]
