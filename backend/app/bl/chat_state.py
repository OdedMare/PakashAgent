"""What one manager-chat turn starts from: the facts the model reads first.

Split from `chat_reply.py`, which runs the rounds; this only gathers. The
payload's order is load-bearing — the stable context comes first so inference
servers can reuse its prefix across rounds and across turns
(`chat_reply._model_input`, in `PAYLOAD_ORDER`).
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
# Slowest-changing first. A server reuses a prompt's prefix only up to its
# first changed byte, so the team's setup and the period lead, the
# conversation (which only grows) follows, and this turn's own request ends
# the turn's fixed part. Alphabetical order put the conversation ahead of the
# profile and the schedule, and every new turn recomputed both. A key not
# named here goes after these, in the order the payload holds it.
PAYLOAD_ORDER = (
    "profile_sections", "profile", "closures", "schedule", "preferences",
    "availability", "history", "focused_schedule_id", "visible_week",
    "focused_date", "conversation", "history_since_last_reply",
    "current_request",
)


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


def schedule_for_chat(schedule):
    """The period as the chat model reads it: per date and shift, how many
    the slot needs and who is on it.

    The projection the change agent reads carries every row's reason, which
    on a hundred-person month is most of the turn's input -- 156K characters
    against 18K here -- and is re-sent on every round. A reason is one
    `employee_state` call away when a question needs it. Code that reads the
    payload (`absence/`, the fast paths) still gets the full projection: this
    is applied only where the payload is written out for the model.
    """
    if not isinstance(schedule, dict) or not (schedule.get("slots") or schedule.get("assignments")):
        return schedule
    days = {}
    for slot in schedule.get("slots") or []:
        days.setdefault(slot["date"], {})[slot["shift"]] = {"need": slot.get("headcount", 1), "on": []}
    for row in schedule.get("assignments") or []:
        cell = days.setdefault(row["date"], {}).setdefault(row["shift"], {"need": 0, "on": []})
        cell["on"].append(row["employee"])
    return {"starts_on": schedule.get("starts_on"), "ends_on": schedule.get("ends_on"),
            "days": {date: days[date] for date in sorted(days)}}


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
        "profile": profile, "profile_sections": PROFILE_SECTIONS,
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
