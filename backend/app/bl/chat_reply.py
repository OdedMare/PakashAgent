"""Run the read-only model loop for one manager-chat turn."""

import datetime
import json
import logging
from dataclasses import dataclass, field

from app.bl.changes.agent import _closures_for_model, _schedule_for_model
from app.bl.changes.values import json_default
from app.bl.chat_fast import ChatFastAnswers
from app.bl.chat_contract import NeedsManager, RejectedPlan, normalize_day_turn, normalize_week_turn, plan_for_model
from app.bl.chat_schema import CHAT_SCHEMA, PROFILE_SECTIONS
from app.bl.planner.shaping import question
from app.bl.shared import add_usage, usage_of
from app.bl.shared import iso
from app.common.errors import AgentError, AppError
from app.common.time_context import agent_time_context, israel_today

_log = logging.getLogger("pakash.chat")
_ROUNDS = 7
_REPAIRS = 2
_MAX_CALLS = 4
_AVAILABILITY_LOOKBACK_DAYS = 7
_ROW_NOISE = ("id", "team_id", "created_at")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)


def _model_input(payload, results, final):
    """Keep the stable context first so inference servers can reuse its prefix."""
    tail = _json({"final_round": final, "results": results})
    return _json(payload)[:-1] + ", " + tail[1:]


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


def _turn_usage(usage, rounds):
    return dict(usage, model_rounds=rounds)


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


class ManagerChatReply:
    def __init__(self, repository, llm, context, tools, planner):
        self._repo = repository
        self._llm = llm
        self._context = context
        self._tools = tools
        self._planner = planner
        self._fast = ChatFastAnswers(repository, context, tools, planner)

    def run(self, team_id, manager_id, chat_id, message_id):
        state = None
        try:
            chat = self._repo.get_chat(team_id, manager_id, chat_id)
            message = next(row for row in chat["messages"] if row["id"] == message_id)
            if message["status"] != "working":
                return
            state = self._state(team_id, chat_id, message_id, chat, message)
            if self._fast.handle(state):
                return
            self._rounds(state)
            self._finish(state)
        except Exception as exc:
            self._error(chat_id, message_id, state, exc)

    def try_fast(self, team_id, manager_id, chat_id, message_id):
        """Answer inside the request when code alone can; the queued job then
        finds the turn finished (or, winning the race, takes this same path)."""
        try:
            chat = self._repo.get_chat(team_id, manager_id, chat_id)
            message = next(row for row in chat["messages"] if row["id"] == message_id)
            return message["status"] == "working" and self._fast.handle(
                self._state(team_id, chat_id, message_id, chat, message))
        except Exception:
            _log.exception("inline chat answer failed; the worker will answer")
            return False

    def _state(self, team_id, chat_id, message_id, chat, message):
        context = message["payload"]
        schedule_id = context.get("schedule_id") or ""
        schedule = self._repo.get_schedule(schedule_id, team_id) if schedule_id else None
        profile = self._context.profile(team_id)
        clock = agent_time_context()
        conversation = self._tools.conversation(chat, message_id)
        request = next((
            row["content"] for row in reversed(conversation) if row["role"] == "user"
        ), "")
        payload = {
            "clock": clock, "profile": profile, "profile_sections": PROFILE_SECTIONS,
            "focused_schedule_id": schedule_id,
            "visible_week": context.get("visible_week") or "",
            "focused_date": context.get("focus_date") or "",
            "schedule": _schedule_for_model(schedule or {}),
            "closures": _closures_for_model(profile, schedule or {}),
            "availability": _availability_for_model(self._repo.availability(
                team_id, starts_on=_availability_since(schedule))),
            "preferences": self._context.active_preferences(team_id),
            "history": self._repo.change_log(team_id, limit=12),
            "conversation": conversation,
            "current_request": request,
        }
        return ReplyState(
            team_id, chat_id, message_id, context, schedule_id, profile,
            clock, request, payload,
        )

    def _rounds(self, state):
        for round_ in range(_ROUNDS):
            final = round_ == _ROUNDS - 1
            state.model_rounds += 1
            state.turn = self._llm.complete_json(
                self._tools.system_prompt, _model_input(state.payload, state.results, final),
                schema=CHAT_SCHEMA, flow="planner", time_context=state.clock,
            )
            if not isinstance(state.turn, dict):
                raise AgentError("הסוכן החזיר תשובה לא תקינה. אפשר לנסות שוב")
            state.usage = add_usage(state.usage, usage_of(state.turn))
            state.turn.pop("_usage", None)
            if state.turn.get("tool_calls") and not final:
                self._tool_calls(state)
                continue
            try:
                if self._prepare(state, final):
                    continue
            except NeedsManager as exc:
                state.plan, state.asked, state.task = None, str(exc), exc.task
                state.results.extend(exc.results)
            except RejectedPlan as exc:
                if final or state.repairs >= _REPAIRS:
                    raise
                state.repairs += 1
                state.results.append({"tool": "plan_check", "ok": False, "error": str(exc)})
                state.steps.append({"tool": "plan_check", "ok": False})
                self._progress(state)
                continue
            break

    def _tool_calls(self, state):
        calls = state.turn.get("tool_calls") or []
        for call in calls[_MAX_CALLS:]:
            state.results.append({
                "tool": call.get("tool"), "ok": False,
                "error": "נדחה: עד %d בדיקות בכל סבב" % _MAX_CALLS,
            })
        for call in calls[:_MAX_CALLS]:
            name, arguments = call.get("tool"), call.get("arguments") or {}
            arguments = self._tools.focus_arguments(
                name, arguments, state.schedule_id, state.context,
            )
            if arguments is None:
                result = {"tool": name, "ok": False, "error": "יש לבחור שבוע או לציין תאריך"}
            else:
                try:
                    result = self._tools.run(
                        state.team_id, name, arguments, state.schedule_id,
                    )
                except AppError as exc:
                    result = {"tool": name, "ok": False, "error": str(exc)}
            state.results.append(result)
            state.steps.append({"tool": name, "ok": result.get("ok", True)})
        self._progress(state)

    def _prepare(self, state, final):
        turn = normalize_day_turn(
            state.turn, state.request, state.context, state.profile,
        )
        state.turn = normalize_week_turn(
            turn, state.request, state.context, state.profile,
        )
        if not (state.turn.get("reply") or "").strip() \
                and not question(state.turn.get("question")):
            raise RejectedPlan(
                "חסרה תשובה למנהל. יש להסביר את התוכנית או לענות לבקשה הנוכחית באופן קונקרטי"
            )
        choices = [
            row["content"] for row in state.payload["conversation"][-8:]
            if row["role"] == "user"
        ]
        if state.turn.get("kind") in ("generate", "restructure"):
            self._progress(
                state, activity="מכין שיבוץ ובודק את כל המשמרות בטווח שנבחר…",
            )
        state.plan = self._planner.prepare(
            state.team_id, state.turn, state.schedule_id, state.request, choices,
        )
        warnings = (state.plan or {}).get("warnings") or []
        needs_review = (
            state.plan and state.plan["kind"] in ("changes", "generate")
            and any(
                row.get("severity") == "warning"
                and row["code"] not in ("unfilled", "missing_role", "missing_commander")
                for row in warnings
            )
            and not state.plan["exceptions"] and not state.reviewed and not final
        )
        if needs_review:
            state.reviewed = True
            state.results.append({
                "tool": "plan_review", "ok": True,
                "plan": plan_for_model(state.plan, whole=True),
            })
            state.steps.append({"tool": "plan_review", "ok": True})
            self._progress(state)
        return needs_review

    def _finish(self, state):
        output = {
            "steps": state.steps, "results": state.results,
            "question": None if state.asked or state.plan else question(
                state.turn.get("question")
            ),
            "_usage": _turn_usage(state.usage, state.model_rounds),
        }
        if state.task:
            output["task"] = state.task
        if state.plan:
            output["plan"] = state.plan
        reply = state.asked or (state.turn.get("reply") or "").strip()
        coverage = (state.plan or {}).get("coverage") or {}
        if coverage and not coverage["complete"]:
            gaps = [
                "%s · %s (%s/%s)" % (
                    row["date"], row["shift"], row["assigned"],
                    row["required"] if row["required"] is not None else "תקינה לא ידועה",
                ) for row in coverage["slots"] if not row["complete"]
            ]
            reply = "הכנתי תוכנית חלקית לאישור. המשמרות שעדיין דורשות טיפול:\n" + \
                    "\n".join("- " + value for value in gaps)
        if not reply and output["question"]:
            reply = output["question"]["question"]
        self._repo.finish_chat_turn(
            state.chat_id, state.message_id, reply or "מה תרצה לבדוק בסידור?",
            "pending" if state.plan else "complete", json.loads(_json(output)),
        )
        _log.info(
            "chat usage rounds=%d prompt=%d completion=%d total=%d",
            state.model_rounds, state.usage["prompt_tokens"],
            state.usage["completion_tokens"], state.usage["total_tokens"],
        )

    def _progress(self, state, **extra):
        self._repo.chat_turn_progress(
            state.chat_id, state.message_id,
            dict(state.context, steps=state.steps, **extra),
        )

    def _error(self, chat_id, message_id, state, exc):
        usage = state.usage if state else {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        }
        usage = add_usage(usage, getattr(exc, "usage", {}))
        rounds, steps = (state.model_rounds, state.steps) if state else (0, [])
        _log.exception("chat reply failed chat=%s message=%s", chat_id, message_id)
        content = str(exc) if isinstance(exc, AppError) else \
            "לא הצלחתי להשלים את הבקשה. לא בוצע שינוי בסידור; אפשר לנסות שוב"
        self._repo.finish_chat_turn(chat_id, message_id, content, "error", {
            "steps": steps, "_usage": _turn_usage(usage, rounds),
        })
