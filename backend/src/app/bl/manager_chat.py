"""Conversation orchestration over the existing model, tools and services.

No model call has write access. A stored plan is validated and applied only
under a separate, private, atomic approval. Background replies are read-only.
"""

import datetime
import json
import logging
from dataclasses import dataclass, field

from app.bl.changes.agent import _closures_for_model, _schedule_for_model
from app.bl.changes.values import json_default
from app.bl.chat_schema import CHAT_SCHEMA, PROFILE_SECTIONS
from app.bl.chat_apply import ChatPlanApplier
from app.bl.chat_planner import ChatPlanBuilder
from app.bl.chat_tools import ManagerChatTools
from app.bl.chat_contract import (
    NeedsManager as _NeedsManager, RejectedPlan as _Rejected,
    approval_text, normalize_day_turn, normalize_week_turn,
    confirmation_question, plan_for_model as _plan_for_model,
)
from app.bl.planner.shaping import question
from app.bl.profile_service import ProfileService
from app.bl.prompts import load
from app.bl.schedule_service.context import ScheduleContext
from app.bl.scheduler.span_audit import add_usage, usage_of
from app.bl.tools import TOOL_DESCRIPTIONS
from app.bl.tools.values import iso
from app.common.errors import AgentError, AppError, ConflictError
from app.common.time_context import agent_time_context, israel_today

_log = logging.getLogger("pakash.chat")
_EXTRA_TOOLS = {
    "list_periods": "כל הסידורים השמורים של הצוות ותאריכיהם",
    "workload_report": "השוואת שעות, מספר משמרות וכוננויות בכל טווח תאריכים",
    "change_history": "מה השתנה בסידורים ומדוע",
    "simulate_changes": "בדיקת מה יקרה אם מבצעים כמה שינויים יחד, כולל כיסוי ועומסים; ללא שמירה",
    "constraints_report": "אילוצים שמורים וקבועים, שעות ועדיפות, בקשות שממתינות לאישור, וכיבוד או התנגשות מול כל הסידורים בטווח",
    "request_inbox": "בקשות אילוץ והחלפות של הצוות, עם מזהים וסטטוסים אמיתיים להחלטת מנהל",
    "preference_list": "כל ההעדפות השמורות של הצוות: פעילות, מוצעות ומושבתות, עם מזהים לעריכה",
}
_ROUNDS = 7      # model calls per turn; the last one may not request tools
_REPAIRS = 2     # times a rejected plan is handed back to the model to fix
_MAX_CALLS = 4   # tool calls the model may request per round
_FULL_RESULTS = 2  # earlier turns whose tool results the model re-reads in full
# Past constraints the model still reads, for "why was Dana off yesterday".
# Older ones arrive through the tools, which take their own date ranges.
_AVAILABILITY_LOOKBACK_DAYS = 7
_ROW_NOISE = ("id", "team_id", "created_at")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)


def _model_input(payload, results, final):
    """One round's input: the turn's fixed context first, this round's last.

    Every round re-sends the whole context, and an inference server reuses
    the prompt prefix it already computed only while the text is identical.
    Sorted keys alone would put `final_round` and `results` mid-object, ahead
    of `profile`, `schedule` and `tools`, so each round recomputed those.
    """
    tail = _json({"final_round": final, "results": results})
    return _json(payload)[:-1] + ", " + tail[1:]


def _availability_since(schedule):
    """The earliest constraint date the model is shown for this turn."""
    recent = (israel_today() - datetime.timedelta(days=_AVAILABILITY_LOOKBACK_DAYS)).isoformat()
    starts = iso((schedule or {}).get("starts_on"))
    return min(recent, starts) if starts else recent


def _availability_for_model(rows):
    return [{key: value for key, value in row.items() if key not in _ROW_NOISE} for row in rows]


def _iso_or_blank(value):
    """A focus day the browser sent, or nothing; never a malformed date."""
    try:
        return datetime.date.fromisoformat(value or "").isoformat()
    except ValueError:
        return ""


def _turn_usage(usage, model_rounds):
    return dict(usage, model_rounds=model_rounds)


@dataclass
class _ReplyState:
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
    usage: dict = field(default_factory=lambda: {
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
    })
    model_rounds: int = 0
    plan: dict = None
    asked: str = ""
    task: dict = None
    repairs: int = 0
    reviewed: bool = False
    turn: dict = None


class ManagerChatService:
    def __init__(self, repository, llm, schedules):
        self._repo, self._llm, self._schedules = repository, llm, schedules
        self._context = ScheduleContext(repository)
        profiles = ProfileService(repository)
        self._chat_tools = ManagerChatTools(repository, schedules, self._context)
        self._planner = ChatPlanBuilder(
            repository, llm, self._context, profiles,
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
        state = None
        try:
            chat = self._repo.get_chat(team_id, manager_id, chat_id)
            message = next(row for row in chat["messages"] if row["id"] == message_id)
            if message["status"] != "working":
                return
            state = self._reply_state(team_id, chat_id, message_id, chat, message)
            if self._finish_fast_reply(state):
                return
            self._run_rounds(state)
            self._finish_reply(state)
        except Exception as exc:
            self._finish_error(team_id, chat_id, message_id, state, exc)

    def _reply_state(self, team_id, chat_id, message_id, chat, message):
        context = message["payload"]
        schedule_id = context.get("schedule_id") or ""
        schedule = self._repo.get_schedule(schedule_id, team_id) if schedule_id else None
        profile = self._context.profile(team_id)
        clock = agent_time_context()
        conversation = self._chat_tools.conversation(chat, message_id)
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
            "tools": dict(TOOL_DESCRIPTIONS, **_EXTRA_TOOLS),
            "current_request": request,
        }
        return _ReplyState(
            team_id, chat_id, message_id, context, schedule_id, profile,
            clock, request, payload,
        )

    def _finish_fast_reply(self, state):
        schedule = state.payload["schedule"] or None
        found = self._chat_tools.replacement_lookup(
            state.team_id, state.request, state.context, schedule, state.profile,
        )
        if not found:
            return False
        reply, output = found
        output["_usage"] = _turn_usage(state.usage, 0)
        self._repo.finish_chat_turn(
            state.chat_id, state.message_id, reply, "complete", output,
        )
        _log.info("chat usage rounds=0 prompt=0 completion=0 total=0")
        return True

    def _run_rounds(self, state):
        for round_ in range(_ROUNDS):
            final = round_ == _ROUNDS - 1
            state.model_rounds += 1
            state.turn = self._llm.complete_json(
                load("manager_chat"),
                _model_input(state.payload, state.results, final),
                schema=CHAT_SCHEMA, flow="planner", time_context=state.clock,
            )
            if not isinstance(state.turn, dict):
                raise AgentError("הסוכן החזיר תשובה לא תקינה. אפשר לנסות שוב")
            state.usage = add_usage(state.usage, usage_of(state.turn))
            state.turn.pop("_usage", None)
            if state.turn.get("tool_calls") and not final:
                self._run_tool_calls(state)
                continue
            try:
                if self._prepare_turn(state, final):
                    continue
            except _NeedsManager as exc:
                state.plan, state.asked, state.task = None, str(exc), exc.task
                state.results.extend(exc.results)
            except _Rejected as exc:
                if final or state.repairs >= _REPAIRS:
                    raise
                state.repairs += 1
                state.results.append({"tool": "plan_check", "ok": False, "error": str(exc)})
                state.steps.append({"tool": "plan_check", "ok": False})
                self._progress(state)
                continue
            break

    def _run_tool_calls(self, state):
        calls = state.turn.get("tool_calls") or []
        for call in calls[_MAX_CALLS:]:
            state.results.append({
                "tool": call.get("tool"), "ok": False,
                "error": "נדחה: עד %d בדיקות בכל סבב" % _MAX_CALLS,
            })
        for call in calls[:_MAX_CALLS]:
            name, arguments = call.get("tool"), call.get("arguments") or {}
            arguments = self._chat_tools.focus_arguments(
                name, arguments, state.schedule_id, state.context,
            )
            if arguments is None:
                result = {"tool": name, "ok": False, "error": "יש לבחור שבוע או לציין תאריך"}
            else:
                try:
                    result = self._chat_tools.run(
                        state.team_id, name, arguments, state.schedule_id,
                    )
                except AppError as exc:
                    result = {"tool": name, "ok": False, "error": str(exc)}
            state.results.append(result)
            state.steps.append({"tool": name, "ok": result.get("ok", True)})
        self._progress(state)

    def _prepare_turn(self, state, final):
        turn = normalize_day_turn(
            state.turn, state.request, state.context, state.profile,
        )
        turn = normalize_week_turn(
            turn, state.request, state.context, state.profile,
        )
        state.turn = turn
        if not (turn.get("reply") or "").strip() and not question(turn.get("question")):
            raise _Rejected(
                "חסרה תשובה למנהל. יש להסביר את התוכנית או לענות לבקשה הנוכחית באופן קונקרטי"
            )
        choices = [
            row["content"] for row in state.payload["conversation"][-8:]
            if row["role"] == "user"
        ]
        if turn.get("kind") in ("generate", "restructure"):
            self._progress(
                state, activity="מכין שיבוץ ובודק את כל המשמרות בטווח שנבחר…",
            )
        state.plan = self._planner.prepare(
            state.team_id, turn, state.schedule_id, state.request, choices,
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
                "plan": _plan_for_model(state.plan, whole=True),
            })
            state.steps.append({"tool": "plan_review", "ok": True})
            self._progress(state)
        return needs_review

    def _finish_reply(self, state):
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
                )
                for row in coverage["slots"] if not row["complete"]
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
        payload = dict(state.context, steps=state.steps, **extra)
        self._repo.chat_turn_progress(state.chat_id, state.message_id, payload)

    def _finish_error(self, team_id, chat_id, message_id, state, exc):
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


    def apply(self, team_id, manager_id, chat_id, message_id, accept_exceptions=False, confirmation=None):
        return self._applier.apply(
            team_id, manager_id, chat_id, message_id,
            accept_exceptions=accept_exceptions, confirmation=confirmation,
        )
