"""Conversation orchestration over the existing model, tools and services.

No model call has write access. A stored plan is validated and applied only
under a separate, private, atomic approval. Background replies are read-only.
"""

import datetime
import logging

from app.bl.absence import AbsenceOptions
from app.bl.chat.apply import ChatPlanApplier
from app.bl.chat.planner import ChatPlanBuilder
from app.bl.chat.reply import ManagerChatReply
from app.bl.chat.tools import ManagerChatTools
from app.bl.chat.contract import (
    approval_text, confirmation_question,
)
from app.bl.profile_service import ProfileService
from app.bl.schedule_service.context import ScheduleContext
from app.common.errors import AgentError, AppError, ConflictError
from app.common.events import CHAT

_log = logging.getLogger("pakash.chat")


# A replacement search past this is a departure, which is `retire`;
# it matches the absence reader's `MAX_DAYS`.
_MAX_ABSENCE_DAYS = 120
# Answers that can be asked for again; a plan still pending may be redone too.
_REDOABLE = ("complete", "error", "cancelled", "pending")
# How much of the old answer the model sees so the new one reads differently.
_PREVIOUS_ANSWER_CHARS = 2000


def _turn_context(request):
    """What the screen showed when the manager sent the message."""
    return {
        "schedule_id": request.get("schedule_id") or "",
        "visible_week": request.get("visible_week") or "",
        "focus_date": _iso_or_blank(request.get("focus_date")),
        "activity": "רגע, קורא את הבקשה…",
    }


def _iso_or_blank(value):
    """A focus day the browser sent, or nothing; never a malformed date."""
    try:
        return datetime.date.fromisoformat(value or "").isoformat()
    except ValueError:
        return ""


def _notifier(events):
    """`events.publish` for chat turns, never raising: a lost signal costs
    one poll interval, a raised one would fail the turn it describes."""
    if events is None:
        return None

    def notify(team_id):
        try:
            events.publish(team_id, CHAT)
        except Exception:  # noqa: BLE001
            _log.warning("chat signal not sent", exc_info=True)
    return notify


class ManagerChatService:
    def __init__(self, repository, llm, schedules, events=None, settings=None):
        self._repo = repository
        self._context = ScheduleContext(repository)
        profiles = ProfileService(repository)
        self._chat_tools = ManagerChatTools(repository, schedules, self._context)
        self._planner = ChatPlanBuilder(
            repository, llm, self._context, profiles, settings,
        )
        self._reply = ManagerChatReply(
            repository, llm, self._context, self._chat_tools, self._planner,
            notify=_notifier(events),
        )
        self._applier = ChatPlanApplier(
            repository, schedules, self._context, profiles,
        )
        self._absence = AbsenceOptions(repository, self._context)

    def start_turn(self, team_id, manager_id, chat_id, request):
        if not request["content"].strip():
            raise AgentError("ההודעה אינה יכולה להיות ריקה")
        replaces = request.get("replaces_message_id") or None
        # An edited request is a new request in the old one's place, never a
        # confirmation of whatever plan happens to be showing.
        if not replaces and self._confirmed(team_id, manager_id, chat_id, request):
            return None
        message_id = self._repo.start_chat_turn(
            team_id, manager_id, chat_id, request["content"].strip(),
            request["request_id"], _turn_context(request), replace_from=replaces,
        )
        if message_id:
            self._reply.try_fast(team_id, manager_id, chat_id, message_id)
        return message_id

    def regenerate(self, team_id, manager_id, chat_id, request):
        """Answer the last request again, in place of the last answer.

        Only an answer can be redone: an applied plan or its receipt is a
        record of a real change, and a turn still running has no answer yet.
        """
        messages = self._repo.get_chat(team_id, manager_id, chat_id)["messages"]
        last = messages[-1] if messages else {}
        if last.get("role") != "assistant" or last.get("status") not in _REDOABLE \
                or (last.get("payload") or {}).get("receipt"):
            raise ConflictError("אין תשובה אחרונה שאפשר לנסח מחדש")
        asked = next((row for row in reversed(messages) if row["role"] == "user"), None)
        if asked is None:
            raise ConflictError("אין בקשה שאפשר לענות עליה מחדש")
        context = dict(_turn_context(request), answer_again=True,
                       previous_answer=(last.get("content") or "")[:_PREVIOUS_ANSWER_CHARS])
        return self._repo.start_chat_turn(
            team_id, manager_id, chat_id, asked["content"], request["request_id"],
            context, replace_from=asked["id"],
        )

    def _confirmed(self, team_id, manager_id, chat_id, request):
        """Whether the message was an approval this call already handled."""
        confirms = approval_text(request["content"])
        if not (request.get("approval_message_id") or confirms):
            return False
        if not confirms:
            raise AgentError("הודעת אישור חייבת לאשר במפורש את התוכנית המוצגת")
        chat = self._repo.get_chat(team_id, manager_id, chat_id)
        if any(row.get("request_id") == request["request_id"] for row in chat["messages"]):
            return True
        latest = chat["messages"][-1] if chat["messages"] else {}
        target = request.get("approval_message_id") or request.get("displayed_plan_id") or latest.get("id")
        if latest.get("id") == target and latest.get("status") == "pending" \
                and latest.get("payload", {}).get("plan") \
                and (not latest["payload"].get("question") or confirmation_question(latest["payload"])):
            self.apply(team_id, manager_id, chat_id, latest["id"], confirmation=request)
            return True
        if request.get("approval_message_id") or request.get("displayed_plan_id"):
            raise ConflictError("אין תוכנית מוצגת שממתינה לאישור. בקשו תוכנית מעודכנת")
        return latest.get("status") == "applied" or bool(latest.get("payload", {}).get("receipt"))

    def reply(self, team_id, manager_id, chat_id, message_id):
        return self._reply.run(team_id, manager_id, chat_id, message_id)

    def apply(self, team_id, manager_id, chat_id, message_id, accept_exceptions=False, confirmation=None):
        return self._applier.apply(
            team_id, manager_id, chat_id, message_id,
            accept_exceptions=accept_exceptions, confirmation=confirmation,
        )

    def replacement_options(self, team_id, employee, starts_on, ends_on):
        """Who could cover one person's absence, fairest first. Reads only.

        The replacement tab's question. The answer is not a plan: the tab
        sends the manager's picks to the conversation, where they become one
        through the ordinary checks and approval.
        """
        names = {row.get("name") for row in self._context.profile(team_id).get("employees") or []}
        if employee not in names:
            raise AppError("העובד לא נמצא בצוות. בחרו שם מהרשימה")
        first = _iso_or_blank(starts_on)
        last = _iso_or_blank(ends_on or starts_on)
        if not first or not last or first > last:
            raise AppError("בחרו תאריך התחלה ותאריך סיום תקינים")
        start = datetime.date.fromisoformat(first)
        days = (datetime.date.fromisoformat(last) - start).days + 1
        if days > _MAX_ABSENCE_DAYS:
            raise AppError("אפשר לחפש מחליפים לעד %d ימים בכל פעם" % _MAX_ABSENCE_DAYS)
        dates = [(start + datetime.timedelta(days=n)).isoformat() for n in range(days)]
        found = self._absence.build(team_id, employee, dates)
        return {key: value for key, value in found.items() if key != "results"}
