"""What one manager-chat turn starts from: the facts the model reads first.

Split from `chat_reply.py`, which runs the rounds; this only gathers. The
payload's order is load-bearing — the stable context comes first so inference
servers can reuse its prefix across rounds (`chat_reply._model_input`).
"""

import datetime
from dataclasses import dataclass, field

from app.bl.changes.agent import _closures_for_model, _schedule_for_model
from app.bl.chat_schema import PROFILE_SECTIONS
from app.bl.shared import iso
from app.common.time_context import agent_time_context, israel_today

_AVAILABILITY_LOOKBACK_DAYS = 7
_HISTORY_ROWS = 12
_ROW_NOISE = ("id", "team_id", "created_at")


@dataclass
class ReplyState:
    team_id: str
    chat_id: str
    message_id: str
    context: dict
    schedule_id: str
    profile: dict
    clock: str
    request: str
    payload: dict
    steps: list = field(default_factory=list)
    results: list = field(default_factory=list)
    usage: dict = field(default_factory=lambda: dict(
        prompt_tokens=0, completion_tokens=0, total_tokens=0,
    ))
    model_rounds: int = 0
    plan: dict = None
    asked: str = ""
    task: dict = None
    repairs: int = 0
    reviewed: bool = False
    turn: dict = None


def _availability_since(schedule):
    recent = (israel_today() - datetime.timedelta(
        days=_AVAILABILITY_LOOKBACK_DAYS,
    )).isoformat()
    starts = iso((schedule or {}).get("starts_on"))
    return min(recent, starts) if starts else recent


def _availability_for_model(rows):
    return [
        {key: value for key, value in row.items() if key not in _ROW_NOISE}
        for row in rows
    ]


def changes_since_reply(history, messages, message_id):
    """How many of `history` (newest first) were logged after the agent last
    answered: edits the manager made on the board, or anybody else made,
    while the conversation was quiet. Zero when there is nothing to compare."""
    replied = [
        row.get("created_at") for row in messages
        if row["role"] == "assistant" and row["id"] != message_id
        and row.get("status") != "working" and row.get("created_at")
    ]
    if not replied:
        return 0
    try:
        return sum(1 for row in history if row.get("created_at") and row["created_at"] > replied[-1])
    except TypeError:
        return 0


def build_state(repository, context_reader, tools, team_id, chat_id, message_id, chat, message):
    context = message["payload"]
    schedule_id = context.get("schedule_id") or ""
    schedule = repository.get_schedule(schedule_id, team_id) if schedule_id else None
    profile = context_reader.profile(team_id)
    clock = agent_time_context()
    conversation = tools.conversation(chat, message_id)
    request = next((
        row["content"] for row in reversed(conversation) if row["role"] == "user"
    ), "")
    history = repository.change_log(team_id, limit=_HISTORY_ROWS)
    payload = {
        "clock": clock, "profile": profile, "profile_sections": PROFILE_SECTIONS,
        "focused_schedule_id": schedule_id,
        "visible_week": context.get("visible_week") or "",
        "focused_date": context.get("focus_date") or "",
        "schedule": _schedule_for_model(schedule or {}),
        "closures": _closures_for_model(profile, schedule or {}),
        "availability": _availability_for_model(repository.availability(
            team_id, starts_on=_availability_since(schedule))),
        "preferences": context_reader.active_preferences(team_id),
        "history": history,
        "history_since_last_reply": changes_since_reply(
            history, chat["messages"], message_id,
        ),
        "conversation": conversation,
        "current_request": request,
    }
    if context.get("answer_again"):
        payload["answer_again"] = {"previous_answer": context.get("previous_answer") or ""}
    return ReplyState(
        team_id, chat_id, message_id, context, schedule_id, profile,
        clock, request, payload,
    )
