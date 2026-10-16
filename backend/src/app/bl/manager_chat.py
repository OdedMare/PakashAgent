"""Conversation orchestration over the existing model, tools and services.

No model call has write access. A stored plan is validated and applied only
under a separate, private, atomic approval. Background replies are read-only.
"""

import datetime

from app.bl.chat_apply import ChatPlanApplier
from app.bl.chat_planner import ChatPlanBuilder
from app.bl.chat_reply import ManagerChatReply
from app.bl.chat_tools import ManagerChatTools
from app.bl.chat_contract import (
    approval_text, confirmation_question,
)
from app.bl.profile_service import ProfileService
from app.bl.schedule_service.context import ScheduleContext
from app.common.errors import AgentError, ConflictError

def _iso_or_blank(value):
    """A focus day the browser sent, or nothing; never a malformed date."""
    try:
        return datetime.date.fromisoformat(value or "").isoformat()
    except ValueError:
        return ""


class ManagerChatService:
    def __init__(self, repository, llm, schedules):
        self._repo, self._llm, self._schedules = repository, llm, schedules
        self._context = ScheduleContext(repository)
        profiles = ProfileService(repository)
        self._chat_tools = ManagerChatTools(repository, schedules, self._context)
        self._planner = ChatPlanBuilder(
            repository, llm, self._context, profiles,
        )
        self._reply = ManagerChatReply(
            repository, llm, self._context, self._chat_tools, self._planner,
        )
        self._applier = ChatPlanApplier(
            repository, schedules, self._context, profiles,
        )

    def start_turn(self, team_id, manager_id, chat_id, request):
        if not request["content"].strip():
            raise AgentError("ההודעה אינה יכולה להיות ריקה")
        confirms = approval_text(request["content"])
        if request.get("approval_message_id") or confirms:
            if not confirms:
                raise AgentError("הודעת אישור חייבת לאשר במפורש את התוכנית המוצגת")
            chat = self._repo.get_chat(team_id, manager_id, chat_id)
            if any(row.get("request_id") == request["request_id"] for row in chat["messages"]):
                return None
            latest = chat["messages"][-1] if chat["messages"] else {}
            target = request.get("approval_message_id") or request.get("displayed_plan_id") or latest.get("id")
            if latest.get("id") == target and latest.get("status") == "pending" \
                    and latest.get("payload", {}).get("plan") \
                    and (not latest["payload"].get("question") or confirmation_question(latest["payload"])):
                self.apply(team_id, manager_id, chat_id, latest["id"], confirmation=request)
                return None
            if request.get("approval_message_id") or request.get("displayed_plan_id"):
                raise ConflictError("אין תוכנית מוצגת שממתינה לאישור. בקשו תוכנית מעודכנת")
            if latest.get("status") == "applied" or latest.get("payload", {}).get("receipt"):
                return None
        return self._repo.start_chat_turn(
            team_id, manager_id, chat_id, request["content"].strip(),
            request["request_id"], {
                "schedule_id": request.get("schedule_id") or "",
                "visible_week": request.get("visible_week") or "",
                "focus_date": _iso_or_blank(request.get("focus_date")),
                "activity": "הבקשה נשמרה וממתינה להתחלת העבודה…",
            },
        )

    def reply(self, team_id, manager_id, chat_id, message_id):
        return self._reply.run(team_id, manager_id, chat_id, message_id)

    def apply(self, team_id, manager_id, chat_id, message_id, accept_exceptions=False, confirmation=None):
        return self._applier.apply(
            team_id, manager_id, chat_id, message_id,
            accept_exceptions=accept_exceptions, confirmation=confirmation,
        )
