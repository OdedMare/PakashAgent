"""Run the read-only model loop for one manager-chat turn."""

import json
import logging

from app.bl.changes.values import json_default
from app.bl.chat_draft import ReplyDraft
from app.bl.chat_fast import ChatFastAnswers
from app.bl.chat_contract import NeedsManager, RejectedPlan, normalize_day_turn, normalize_week_turn, plan_for_model
from app.bl.chat_schema import CHAT_SCHEMA, suggestions
from app.bl.chat_state import PAYLOAD_ORDER, build_state
from app.bl.planner.shaping import question
from app.bl.shared import add_usage, usage_of
from app.common.errors import AgentError, AppError

_log = logging.getLogger("pakash.chat")
_ROUNDS = 7
_REPAIRS = 2
_MAX_CALLS = 4


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)


def _model_input(payload, results, final):
    """Keep the stable context first so inference servers can reuse its prefix."""
    keys = [key for key in PAYLOAD_ORDER if key in payload]
    keys += [key for key in payload if key not in PAYLOAD_ORDER]
    fields = [(key, payload[key]) for key in keys]
    fields += [("final_round", final), ("results", results)]
    return "{" + ", ".join(_json(key) + ": " + _json(value) for key, value in fields) + "}"


def _turn_usage(usage, rounds):
    return dict(usage, model_rounds=rounds)


class ManagerChatReply:
    def __init__(self, repository, llm, context, tools, planner, notify=None):
        self._repo = repository
        # Wakes the manager's screen to re-read the turn (`common/events.py`);
        # the poll stays underneath for a missed signal.
        self._notify = notify or (lambda team_id: None)
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
            # Code answers the same sentence the same way every time, so a
            # request to answer again goes to the model.
            if not state.context.get("answer_again") and self._fast.handle(state):
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
        return build_state(
            self._repo, self._context, self._tools,
            team_id, chat_id, message_id, chat, message,
        )

    def _rounds(self, state):
        for round_ in range(_ROUNDS):
            final = round_ == _ROUNDS - 1
            state.model_rounds += 1
            state.turn = self._llm.complete_json(
                self._tools.system_prompt, _model_input(state.payload, state.results, final),
                schema=CHAT_SCHEMA, flow="planner", time_context=state.clock,
                on_text=self._draft(state),
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
                    raise AgentError(
                        "לא הצלחתי להכין תוכנית תקינה: %s. לא בוצע שינוי בסידור; "
                        "אפשר לנסח את הבקשה מחדש או לפצל אותה" % str(exc).rstrip(".")
                    ) from exc
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
        offered = [] if state.asked else suggestions(state.turn.get("suggestions"))
        if offered:
            output["suggestions"] = offered
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
        if (state.plan or {}).get("solver_note"):
            reply = "\n\n".join(part for part in (reply, state.plan["solver_note"]) if part)
        if not reply and output["question"]:
            reply = output["question"]["question"]
        self._repo.finish_chat_turn(
            state.chat_id, state.message_id, reply or "מה תרצה לבדוק בסידור?",
            "pending" if state.plan else "complete", json.loads(_json(output)),
        )
        self._notify(state.team_id)
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
        self._notify(state.team_id)

    def _draft(self, state):
        def write(text):
            self._repo.chat_turn_draft(state.chat_id, state.message_id, text)
            self._notify(state.team_id)
        return ReplyDraft(write)

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
        if state:
            self._notify(state.team_id)
