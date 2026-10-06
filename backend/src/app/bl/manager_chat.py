"""Conversation orchestration over the existing model, tools and services.

No model call has write access. A stored plan is validated and applied only
under a separate, private, atomic approval. Background replies are read-only.
"""

import datetime
import hashlib
import json
import logging

from app.bl.audit import shift_stats
from app.bl.changes.agent import _closures_for_model, _schedule_for_model
from app.bl.changes.proposal import build_proposal
from app.bl.changes.values import json_default
from app.bl.chat_schema import CHAT_SCHEMA, PROFILE_SECTIONS
from app.bl.chat_contract import (
    NeedsManager as _NeedsManager, RejectedPlan as _Rejected,
    approval_text, add_coverage, audit_plan, exception_warnings, whole_day_request, normalize_day_turn,
    normalize_week_turn, draft_schedule_ids, confirmation_question,
)
from app.bl.chat_lifecycle import future_schedules, prepare_retirement, prepare_structure
from app.bl.chat_generation import prepare_generation
from app.bl.planner.shaping import question
from app.bl.placement.values import warning_key
from app.bl.profile_service import ProfileService
from app.bl.prompts import load
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.generation.history import AssignmentHistory
from app.bl.schedule_service.operations import OperationApplier
from app.bl.scheduler import Scheduler
from app.bl.simulate.hypothetical import Hypothetical, schedule_rows
from app.bl.tools import ScheduleTools, TOOL_DESCRIPTIONS
from app.bl.tools.schedule_tools import _invalid_date_argument
from app.bl.tools.values import iso
from app.common.errors.errors import AgentError, AppError, ConflictError
from app.common.time_context.time_context import agent_time_context, israel_today

_log = logging.getLogger("pakash.chat")
_EXTRA_TOOLS = {
    "list_periods": "כל הסידורים השמורים של הצוות ותאריכיהם",
    "workload_report": "השוואת שעות, מספר משמרות וכוננויות בכל טווח תאריכים",
    "change_history": "מה השתנה בסידורים ומדוע",
    "simulate_changes": "בדיקת מה יקרה אם מבצעים כמה שינויים יחד, כולל כיסוי ועומסים; ללא שמירה",
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


def _plan_for_model(plan, whole):
    """A stored plan as the model reads it back: whole, or as a summary."""
    # The snapshot hash and the generated slot grid mean nothing to the model.
    shown = {key: value for key, value in plan.items()
             if key not in ("snapshot", "updated_profile", "replacement_slots", "creation_slots")}
    if shown.get("generated"):
        shown["generated"] = {key: value for key, value in shown["generated"].items() if key != "slots"}
    if whole:
        return shown
    summary = {key: shown[key] for key in ("kind", "schedule_id", "starts_on", "ends_on", "reason",
                                           "agent_reason", "replace_existing") if key in shown}
    return dict(summary, summarized=True,
                operations=len(shown.get("operations") or []),
                constraints=len(shown.get("constraints") or []),
                generated_assignments=len((shown.get("generated") or {}).get("assignments") or []))


def _fingerprint(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class ManagerChatService:
    def __init__(self, repository, llm, schedules):
        self._repo, self._llm, self._schedules = repository, llm, schedules
        self._context = ScheduleContext(repository)
        self._tools = ScheduleTools(repository)
        self._profiles = ProfileService(repository)
        self._scheduler = Scheduler(llm)
        self._history = AssignmentHistory(repository)

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
            },
        )

    def reply(self, team_id, manager_id, chat_id, message_id):
        steps = []
        try:
            chat = self._repo.get_chat(team_id, manager_id, chat_id)
            message = next(row for row in chat["messages"] if row["id"] == message_id)
            if message["status"] != "working":
                return
            context = message["payload"]
            schedule_id = context.get("schedule_id") or ""
            schedule = self._repo.get_schedule(schedule_id, team_id) if schedule_id else None
            profile = self._context.profile(team_id)
            # One clock for every round, so the rounds' prompts share a prefix.
            clock = agent_time_context()
            payload = {
                "clock": clock, "profile": profile,
                "profile_sections": PROFILE_SECTIONS,
                "focused_schedule_id": schedule_id,
                "visible_week": context.get("visible_week") or "",
                "focused_date": context.get("focus_date") or "",
                "schedule": _schedule_for_model(schedule or {}),
                "closures": _closures_for_model(profile, schedule or {}),
                "availability": _availability_for_model(self._repo.availability(
                    team_id, starts_on=_availability_since(schedule))),
                "preferences": self._context.active_preferences(team_id),
                "history": self._repo.change_log(team_id, limit=12),
                "conversation": self._conversation(chat, message_id),
                "tools": dict(TOOL_DESCRIPTIONS, **_EXTRA_TOOLS),
            }
            results, steps = [], []
            plan, asked, repairs, task = None, "", 0, None
            reviewed = False
            request = next((row["content"] for row in reversed(payload["conversation"])
                            if row["role"] == "user"), "")
            payload["current_request"] = request
            for round_ in range(_ROUNDS):
                final = round_ == _ROUNDS - 1
                turn = self._llm.complete_json(
                    load("manager_chat"), _model_input(payload, results, final),
                    schema=CHAT_SCHEMA, flow="planner", time_context=clock,
                )
                if not isinstance(turn, dict):
                    raise AgentError("הסוכן החזיר תשובה לא תקינה. אפשר לנסות שוב")
                calls = turn.get("tool_calls") or []
                if calls and not final:
                    for call in calls[_MAX_CALLS:]:
                        results.append({"tool": call.get("tool"), "ok": False,
                                        "error": "נדחה: עד %d בדיקות בכל סבב" % _MAX_CALLS})
                    for call in calls[:_MAX_CALLS]:
                        name, arguments = call.get("tool"), call.get("arguments") or {}
                        arguments = self._focus_arguments(name, arguments, schedule_id, context)
                        if arguments is None:
                            results.append({"tool": name, "ok": False, "error": "יש לבחור שבוע או לציין תאריך"})
                            steps.append({"tool": name, "ok": False})
                            continue
                        try:
                            result = self._run_tool(team_id, name, arguments, schedule_id)
                        except AppError as exc:
                            # A refused read is a fact for the model, not the end of the turn.
                            result = {"tool": name, "ok": False, "error": str(exc)}
                        results.append(result)
                        steps.append({"tool": name, "ok": result.get("ok", True)})
                    # The browser polls the working message; it shows each check as it lands.
                    self._repo.chat_turn_progress(chat_id, message_id, dict(context, steps=steps))
                    continue
                try:
                    turn = normalize_day_turn(turn, request, context, profile)
                    turn = normalize_week_turn(turn, request, context, profile)
                    if not (turn.get("reply") or "").strip() and not question(turn.get("question")):
                        raise _Rejected("חסרה תשובה למנהל. יש להסביר את התוכנית או לענות לבקשה הנוכחית באופן קונקרטי")
                    choices = [row["content"] for row in payload["conversation"][-8:] if row["role"] == "user"]
                    if turn.get("kind") in ("generate", "restructure"):
                        self._repo.chat_turn_progress(chat_id, message_id, dict(context, steps=steps,
                            activity="מכין שיבוץ ובודק את כל המשמרות בטווח שנבחר…"))
                    plan = self._prepare_plan(team_id, turn, schedule_id, request, choices)
                    if plan and plan["kind"] in ("changes", "generate") \
                            and any(row.get("severity") == "warning" and row["code"] not in
                                    ("unfilled", "missing_role", "missing_commander")
                                    for row in plan["warnings"]) \
                            and not plan["exceptions"] and not reviewed and not final:
                        # Give the agent the combined result once, before the
                        # manager sees it. Warnings remain advisory: a named
                        # choice may stand with its exact conflicts explained.
                        reviewed = True
                        results.append({"tool": "plan_review", "ok": True,
                                        "plan": _plan_for_model(plan, whole=True)})
                        steps.append({"tool": "plan_review", "ok": True})
                        self._repo.chat_turn_progress(chat_id, message_id, dict(context, steps=steps))
                        continue
                except _NeedsManager as exc:
                    plan = None
                    asked = str(exc)
                    results.extend(exc.results)
                    task = exc.task
                except _Rejected as exc:
                    if final or repairs >= _REPAIRS:
                        raise
                    # The code refused the plan; the model sees why and revises it.
                    repairs += 1
                    results.append({"tool": "plan_check", "ok": False, "error": str(exc)})
                    steps.append({"tool": "plan_check", "ok": False})
                    self._repo.chat_turn_progress(chat_id, message_id, dict(context, steps=steps))
                    continue
                break
            output = {"steps": steps, "results": results,
                      "question": None if asked or plan else question(turn.get("question"))}
            if task:
                output["task"] = task
            if plan:
                output["plan"] = plan
            reply = asked or (turn.get("reply") or "").strip()
            if plan and plan.get("coverage") and not plan["coverage"]["complete"]:
                gaps = ["%s · %s (%s/%s)" % (row["date"], row["shift"], row["assigned"],
                        row["required"] if row["required"] is not None else "תקינה לא ידועה")
                        for row in plan["coverage"]["slots"] if not row["complete"]]
                reply = "הכנתי תוכנית חלקית לאישור. המשמרות שעדיין דורשות טיפול:\n" + \
                        "\n".join("- " + value for value in gaps)
            if not reply and output["question"]:
                reply = output["question"]["question"]
            self._repo.finish_chat_turn(
                chat_id, message_id, reply or "מה תרצה לבדוק בסידור?",
                "pending" if plan else "complete", json.loads(_json(output)),
            )
        except Exception as exc:
            _log.exception("chat reply failed chat=%s message=%s", chat_id, message_id)
            content = str(exc) if isinstance(exc, AppError) else \
                "לא הצלחתי להשלים את הבקשה. לא בוצע שינוי בסידור; אפשר לנסות שוב"
            self._repo.finish_chat_turn(chat_id, message_id, content, "error", {"steps": steps})

    @staticmethod
    def _focus_arguments(name, arguments, schedule_id, context):
        """Aim a dateless read at the week on screen; None when nothing is."""
        if (name not in TOOL_DESCRIPTIONS and name != "simulate_changes") or arguments.get("schedule_id") \
                or arguments.get("day") or arguments.get("slot_date"):
            return arguments
        if schedule_id:
            return dict(arguments, schedule_id=schedule_id)
        if name in ("read_period", "employee_state", "coverage_gaps", "publish_readiness", "simulate_changes"):
            if not context.get("visible_week"):
                return None
            return dict(arguments, day=context["visible_week"])
        return arguments

    def _conversation(self, chat, working_id):
        """Earlier turns, with only the recent ones carried in full.

        Every round of every turn re-sends this, so stale bulk is paid for
        many times over and crowds out the facts that matter. The newest plan
        stays whole, because "instead use Dana" revises it; the last checked
        facts stay whole, because "the second person" points into them.
        Anything older is a summary of what was proposed and what became of it.
        """
        all_rows = [row for row in chat["messages"] if row["id"] != working_id]
        retained = set(range(max(0, len(all_rows) - 32), len(all_rows)))
        for key in ("plan", "question", "results", "task"):
            anchor = next((index for index in range(len(all_rows) - 1, -1, -1)
                           if (all_rows[index].get("payload") or {}).get(key)), None)
            if anchor is not None:
                retained.add(anchor)
                if anchor:
                    retained.add(anchor - 1)
                if anchor + 1 < len(all_rows):
                    retained.add(anchor + 1)
        rows = [all_rows[index] for index in sorted(retained)]
        planned = [index for index, row in enumerate(rows) if (row.get("payload") or {}).get("plan")]
        checked = [index for index, row in enumerate(rows) if (row.get("payload") or {}).get("results")]
        latest_plan = planned[-1] if planned else -1
        recent_results = set(checked[-_FULL_RESULTS:])
        result = []
        for index, row in enumerate(rows):
            item = {"role": row["role"], "content": row["content"], "status": row["status"]}
            payload = row.get("payload") or {}
            context = {}
            if payload.get("task"):
                context["task"] = payload["task"]
            if payload.get("question"):
                context["question"] = payload["question"]
            if index in recent_results:
                context["results"] = payload["results"]
            elif payload.get("steps"):
                context["checked"] = sorted({step["tool"] for step in payload["steps"]})
            if payload.get("plan"):
                context["plan"] = _plan_for_model(payload["plan"], whole=index == latest_plan)
            item["context"] = context
            result.append(item)
        return result

    def _run_tool(self, team_id, name, arguments, focused_id):
        invalid = _invalid_date_argument(arguments)
        if invalid:
            return {"tool": name, "ok": False, "error": "נדרש תאריך מוחלט עבור " + invalid}
        if name == "list_periods":
            return {"tool": name, "ok": True, "periods": self._repo.list_schedules(team_id)}
        if name == "change_history":
            return {"tool": name, "ok": True, "changes": self._repo.change_log(team_id, limit=60)}
        if name == "workload_report":
            return dict(self._workload(team_id, arguments, focused_id), tool=name, ok=True)
        if name == "simulate_changes":
            period = self._tools.run(team_id, "read_period", {
                key: arguments[key] for key in ("schedule_id", "day") if arguments.get(key)
            }) if arguments.get("schedule_id") or arguments.get("day") else None
            schedule_id = ((period or {}).get("schedule") or {}).get("id") or focused_id
            if (period and not period.get("found")) or not schedule_id:
                return {"tool": name, "ok": False, "error": "יש לבחור סידור קיים או לציין את השבוע"}
            operations = arguments.get("operations") or []
            schedule = self._repo.get_schedule(schedule_id, team_id)
            profile = self._context.profile(team_id)
            proposal = build_proposal(dict(operations=operations), profile,
                                      schedule, "בדיקת תרחיש")
            if proposal["needs_input"] or len(proposal["operations"]) != len(operations):
                raise _Rejected(proposal["reply"] or "יש לציין עובדים, משמרות ותאריכים מוכרים לכל השינויים")
            operations = proposal["operations"]
            # The shared simulator bounds operations. Reject overflow rather
            # than describing a silently truncated scenario as complete.
            rows = self._changed_rows(schedule, operations)
            names = {person["name"] for person in profile.get("employees") or []}
            if any(row["employee"] not in names for row in rows):
                raise _Rejected("יש להשתמש בשמות העובדים המלאים מרשימת הצוות")
            result = self._schedules.simulate(team_id, operations, schedule_id)
            availability = self._repo.availability(team_id)
            before = {warning_key(row): row for row in self._audit_plan(
                profile, schedule, schedule_rows(schedule), availability, [])}
            after = self._audit_plan(profile, schedule, rows, availability, [])
            after_keys = {warning_key(row) for row in after}
            return dict(result, tool=name, ok=True, warnings_after=after,
                        introduced=[row for row in after if warning_key(row) not in before],
                        resolved=[row for key, row in before.items() if key not in after_keys])
        if name == "find_replacements":
            arguments = dict(arguments, include_exceptions=False)
        return self._tools.run(team_id, name, arguments)

    def _workload(self, team_id, arguments, focused_id):
        profile = self._context.profile(team_id)
        first, last = arguments.get("starts_on") or "", arguments.get("ends_on") or ""
        schedule_id = arguments.get("schedule_id") or (focused_id if not first else "")
        if bool(first) != bool(last) or (first and first > last):
            raise AgentError("צריך לציין טווח תאריכים מלא ותקין")
        periods = self._repo.list_schedules(team_id)
        if schedule_id:
            periods = [self._repo.get_schedule(schedule_id, team_id)]
            if not first:
                first, last = iso(periods[0]["starts_on"]), iso(periods[0]["ends_on"])
            elif not (iso(periods[0]["starts_on"]) <= first <= last <= iso(periods[0]["ends_on"])):
                raise AgentError("טווח הדוח חורג מהסידור שנבחר. בחרו את התקופה המתאימה")
        elif not first:
            return {"found": False, "reason": "בחרו שבוע או ציינו טווח תאריכים"}
        assignments, seen, included = [], set(), []
        for period in periods:
            if iso(period["starts_on"]) > last or iso(period["ends_on"]) < first:
                continue
            included.append(period["id"])
            for row in self._repo.assignments(period["id"], team_id):
                key = (row["employee"], iso(row["date"]), row["shift"])
                if first <= key[1] <= last and key not in seen:
                    seen.add(key)
                    assignments.append(dict(row, date=key[1]))
        return {"found": True, "starts_on": first, "ends_on": last,
                "periods": included, "basis": "scheduled",
                "stats": shift_stats(assignments, profile.get("shifts") or [],
                                     profile.get("employees") or [], profile=profile)}

    def _state(self, team_id, schedule_id):
        return {
            "profile": self._context.profile(team_id),
            "availability": self._repo.availability(team_id),
            "preferences": self._context.active_preferences(team_id),
            "schedule": self._repo.get_schedule(schedule_id, team_id) if schedule_id else None,
            "periods": self._repo.list_schedules(team_id) if not schedule_id else [],
        }

    def _prepare_plan(self, team_id, turn, focused_id, request, choices=()):
        kind = turn.get("kind") or "answer"
        if kind == "answer" and confirmation_question(turn):
            raise _Rejected("אין לבקש אישור בלי תוכנית שמורה. לבקשת שינוי יש להכין תוכנית מלאה; להתייעצות יש לענות בלי לבקש אישור ביצוע")
        if turn.get("needs_reason"):
            raise _Rejected("אין צורך לבקש סיבה. הוראת המנהל היא הסיבה; יש להכין את התוכנית או לשאול רק על יעד חסר")
        if turn.get("needs_input"):
            return None
        if (kind != "changes" and (turn.get("operations") or turn.get("constraints"))) \
                or (kind not in ("profile", "restructure") and turn.get("profile_patch_json")) \
                or (kind not in ("generate", "restructure") and turn.get("required_assignments")) \
                or turn.get("profile_operations"):
            raise _Rejected("סוג התשובה אינו תואם לפעולות. הוראת שיבוץ דורשת kind=changes; התייעצות דורשת kind=answer בלי פעולות; עריכת צוות דורשת kind=profile ו-profile_patch_json")
        if kind == "answer":
            return None
        schedule_id = turn.get("schedule_id") or focused_id
        if kind == "generate":
            # A new week's dates must not fall back to the week on screen. An
            # exact period wins; otherwise a period that contains the dates is
            # the one a single day (or a few days) is rebuilt inside.
            first, last = turn.get("starts_on") or "", turn.get("ends_on") or ""
            periods = self._repo.list_schedules(team_id)
            schedule_id = next((period["id"] for period in periods
                                if iso(period["starts_on"]) == first
                                and iso(period["ends_on"]) == last), "") or \
                next((period["id"] for period in periods if first and last
                      and iso(period["starts_on"]) <= first and last <= iso(period["ends_on"])), "")
        state = self._state(team_id, schedule_id)
        schedule, profile = state["schedule"] or {}, state["profile"]
        if kind == "changes" and whole_day_request(request, profile):
            raise _Rejected("בקשת שיבוץ ליום שלם דורשת kind=generate ובדיקת כל המשמרות ביום; אין להחזיר רק שיבוץ בוקר")
        plan = {
            "kind": kind, "schedule_id": schedule_id,
            "agent_reason": (turn.get("agent_reason") or turn.get("reply") or "").strip(),
            "reason": (turn.get("stated_reason") or request).strip(),
            "snapshot": _fingerprint(state), "operations": [], "constraints": [],
            "warnings": [], "exceptions": (turn.get("exceptions") or [])[:20],
        }
        if schedule and kind != "profile":
            plan.update(starts_on=iso(schedule["starts_on"]), ends_on=iso(schedule["ends_on"]))
        if kind == "retire":
            periods = prepare_retirement(self._repo, self._profiles, team_id, turn, plan, state)
            state = dict(state, future_schedules=periods)
            plan["snapshot"] = _fingerprint(state)
            plan["draft_schedule_ids"] = draft_schedule_ids(plan, state)
            return plan
        if kind == "restructure":
            prepare_structure(self._profiles, self._scheduler, team_id, turn, plan, state,
                              self._history.before(team_id, iso(schedule["starts_on"])), self._audit_plan)
            add_coverage(plan, plan["updated_profile"])
            plan["draft_schedule_ids"] = draft_schedule_ids(plan, state)
            return plan
        if kind == "profile":
            try:
                patch = json.loads(turn.get("profile_patch_json") or "{}")
            except ValueError as exc:
                raise _Rejected("עריכת הפרופיל אינה תקינה. אפשר לנסח שוב") from exc
            if not isinstance(patch, dict) or not patch or set(patch) - set(PROFILE_SECTIONS):
                raise _Rejected("לא זוהה שינוי תקין בפרטי הצוות")
            for section in ("employees", "shifts"):
                if section not in patch:
                    continue
                if not isinstance(patch[section], list) or any(not isinstance(row, dict) for row in patch[section]):
                    raise _Rejected("פרטי העובדים והמשמרות חייבים להיות רשימת רשומות")
                existing = {row["name"]: row for row in profile.get(section) or []}
                if section == "employees":
                    for row in patch[section]:
                        required = {"role", "eligible_shifts", "service_type", "exit_pattern", "rotation_group"}
                        missing = required - set(row)
                        if row.get("name") not in existing and missing:
                            raise _Rejected("לעובד החדש חסרים שדות: %s. יש לשמור את הפרטים שהמנהל נתן ולא לנחש" %
                                            ", ".join(sorted(missing)))
                # A missed field must not erase an existing qualification,
                # rotation, trainer flag or note. Explicit values still win.
                patch[section] = [dict(existing.get(row.get("name"), {}), **row) for row in patch[section]]
            try:
                updated = self._profiles.preview(team_id, **patch)
            except AppError as exc:
                raise _Rejected(str(exc)) from exc
            plan["profile_patch"] = patch
            plan["profile_before"] = {key: profile.get(key) for key in patch}
            plan["profile_after"] = {key: updated.get(key) for key in patch}
        elif kind == "generate":
            prepare_generation(self._repo, self._scheduler, self._history, team_id, turn, plan, state)
        else:
            if not schedule and (kind != "changes" or turn.get("operations")):
                raise _Rejected("אין סידור בשבוע הזה. אפשר לבקש לבנות אותו קודם")
            if kind == "changes":
                people = {row["name"]: row for row in profile.get("employees") or []}
                for row in turn.get("operations") or []:
                    person = people.get(row.get("employee"), {})
                    if row.get("action") == "assign" and person.get("inactive_from") \
                            and (row.get("date") or "") >= person["inactive_from"]:
                        raise _Rejected("העובד סיים את העבודה לפני המשמרת. יש לבחור מחליף פעיל")
                if any(not row.get("available", False) for row in turn.get("constraints") or []):
                    selections = "\n".join(list(choices) + [request])
                    assignments = [row for row in turn.get("operations") or [] if row.get("action") == "assign"]
                    unselected = [row for row in assignments if row.get("employee") and row["employee"] not in selections]
                    if unselected:
                        candidates = []
                        for row in unselected:
                            leaving = next((item.get("employee", "") for item in turn.get("operations") or []
                                            if item.get("action") == "remove" and item.get("shift") == row.get("shift")
                                            and item.get("date") == row.get("date")), "")
                            candidates.append(self._tools.run(team_id, "find_replacements", dict(
                                schedule_id=schedule_id, employee=leaving, shift_name=row.get("shift"), slot_date=row.get("date"))))
                        prompt = "בדקתי מועמדים להחלפה. בחרו מי יחליף בכל משמרת כדי שאכין תוכנית מלאה לאישור." \
                            if any(result.get("candidates") for result in candidates) else \
                            "לא נמצאו מחליפים שעומדים בכל הכללים. אפשר לשנות את היקף המשמרת או להוסיף תגבור. איך תרצו לפתור את החוסר?"
                        raise _NeedsManager(prompt, candidates, dict(request=request,
                            constraints=self._constraints(turn.get("constraints") or [], profile)))
                proposal = build_proposal(turn, profile, schedule, plan["reason"])
                if proposal["needs_input"] or proposal["needs_reason"]:
                    raise _NeedsManager(proposal["reply"] or "נדרשים פרטים נוספים לפני שינוי")
                if len(proposal["operations"]) != len(turn.get("operations") or []):
                    raise _Rejected("חלק מהשינויים לא תואמים לסידור. יש לבקש תוכנית מעודכנת")
                plan["operations"] = proposal["operations"]
                plan["constraints"] = self._constraints(turn.get("constraints") or [], profile)
                if not plan["operations"] and not plan["constraints"]:
                    return None
                rows = self._changed_rows(schedule, plan["operations"]) if schedule else []
                names = {person["name"] for person in profile.get("employees") or []}
                if any(row["employee"] not in names for row in rows):
                    raise _Rejected("התוכנית מכילה עובד שאינו נמצא בצוות")
                if schedule:
                    existing = {warning_key(row) for row in self._audit_plan(
                        profile, schedule, schedule_rows(schedule), state["availability"], [])}
                    plan["warnings"] = [row for row in self._audit_plan(
                        profile, schedule, rows, state["availability"], plan["constraints"])
                        if warning_key(row) not in existing]
            elif kind == "clear":
                plan["operations"] = [dict(action="remove", employee=row["employee"],
                                           date=iso(row["date"]), shift=row["shift"],
                                           reason=plan["agent_reason"])
                                      for row in schedule.get("assignments") or []]
            elif kind == "publish":
                plan["warnings"] = self._context.audit_rows(team_id, schedule.get("assignments") or [], schedule)
            elif kind != "unpublish":
                raise _Rejected("הפעולה אינה נתמכת")
        plan["draft_schedule_ids"] = draft_schedule_ids(plan, state)
        return plan

    def _constraints(self, offered, profile):
        names = {row["name"] for row in profile.get("employees") or []}
        shifts = {row["name"] for row in profile.get("shifts") or []}
        result = []
        for row in offered[:126]:
            if row.get("employee") not in names or row.get("shift", "") not in shifts | {""}:
                raise _Rejected("האילוץ חייב להתייחס לעובד ולמשמרת מוכרים")
            try:
                date = datetime.date.fromisoformat(row.get("date") or "").isoformat()
            except ValueError as exc:
                raise _Rejected("תאריך האילוץ אינו תקין") from exc
            result.append(dict(row, date=date, available=bool(row.get("available", False))))
        return result

    def _changed_rows(self, schedule, operations):
        if len(operations) > 40:
            raise _Rejected("התוכנית גדולה מדי. יש לפצל את השינוי לתקופות קצרות יותר")
        imagined = Hypothetical(schedule_rows(schedule), schedule).apply_all(operations)
        if imagined.skipped:
            raise _Rejected(imagined.skipped[0]["why"])
        keys = [(row["employee"], row["shift"], row["date"]) for row in imagined.rows]
        if len(keys) != len(set(keys)):
            raise _Rejected("התוכנית משבצת את אותו עובד פעמיים באותה משמרת. יש להסיר את השיבוץ הכפול")
        return imagined.rows

    _audit_plan = staticmethod(audit_plan)

    def apply(self, team_id, manager_id, chat_id, message_id, accept_exceptions=False, confirmation=None):
        with self._repo.chat_approval(team_id, manager_id, chat_id, message_id) as message:
            if message["status"] == "applied":
                return self._repo.get_chat(team_id, manager_id, chat_id)
            payload = message["payload"]
            plan = payload.get("plan") or {}
            state = self._state(team_id, plan.get("schedule_id") or "")
            if plan.get("kind") == "retire":
                state["future_schedules"] = future_schedules(self._repo, team_id, plan["effective_date"])
            if _fingerprint(state) != plan.get("snapshot"):
                raise ConflictError("הסידור או כללי הצוות השתנו מאז ההמלצה. בקשו תוכנית מעודכנת")
            if (exception_warnings(plan) or plan.get("exceptions")) and not accept_exceptions:
                raise ConflictError("יש לאשר במפורש את החריגות המוצגות בתוכנית")
            reason = plan.get("reason") or message["content"]
            agent_reason = plan.get("agent_reason") or "שינוי שאושר בשיחה"
            conflicts = [row.get("message", "") for row in plan.get("warnings") or []]
            conflicts += plan.get("exceptions") or []
            if conflicts:
                agent_reason += "\nחריגות שאושרו במפורש: " + "; ".join(conflicts)
            kind, schedule_id = plan.get("kind"), plan.get("schedule_id") or ""
            for period_id in plan.get("draft_schedule_ids") or []:
                self._repo.set_schedule_status(period_id, team_id, "draft")
            if kind == "retire":
                for period in plan["affected_schedules"]:
                    for operation in period["operations"]:
                        schedule = self._repo.get_schedule(period["schedule_id"], team_id)
                        if not OperationApplier(self._repo).apply(team_id, schedule, operation, reason, agent_reason):
                            raise ConflictError("לא ניתן לפנות את כל המשמרות. לא בוצע שינוי")
                self._repo.update_team_profile(team_id, plan["updated_profile"])
            elif kind == "restructure":
                schedule = self._repo.get_schedule(schedule_id, team_id)
                for row in schedule["assignments"]:
                    if plan["starts_on"] <= iso(row["date"]) <= plan["ends_on"]:
                        self._repo.remove_assignment(row["id"], team_id)
                self._repo.replace_span_slots(schedule_id, team_id, plan["starts_on"], plan["ends_on"], plan["generated"]["slots"])
                self._repo.update_team_profile(team_id, plan["updated_profile"])
                refreshed = self._repo.get_schedule(schedule_id, team_id)
                slots = {(row["shift_name"], iso(row["slot_date"])): row["id"] for row in refreshed["slots"]}
                for row in plan["generated"]["assignments"]:
                    self._repo.add_assignment(schedule_id, team_id, slots[(row["shift"], iso(row["date"]))],
                                              row["employee"], row.get("reason") or agent_reason,
                                              source=row.get("source") or "agent")
            elif kind == "profile":
                self._profiles.update(team_id, **plan["profile_patch"])
            elif kind == "generate":
                schedule_id = self._commit_generation(team_id, plan, agent_reason)
            elif kind == "publish":
                self._schedules.publish(schedule_id, team_id)
            elif kind == "unpublish":
                self._schedules.unpublish(schedule_id, team_id)
            elif kind in ("changes", "clear"):
                applier = OperationApplier(self._repo)
                for operation in plan["operations"]:
                    schedule = self._repo.get_schedule(schedule_id, team_id)
                    if not applier.apply(team_id, schedule, operation, reason, agent_reason):
                        raise ConflictError("לא ניתן להחיל את כל התוכנית. לא בוצע שינוי")
                for row in plan["constraints"]:
                    self._repo.set_availability(
                        team_id, row["employee"], row["date"], shift_name=row.get("shift") or "",
                        available=row.get("available", False), reason=row.get("reason") or reason,
                        source="agent",
                    )
            else:
                raise AgentError("אין תוכנית להחיל")
            self._repo.append_change(
                team_id, "chat_approved", schedule_id=schedule_id or None,
                reason=reason, agent_reason=agent_reason,
            )
            receipt = "התוכנית הוחלה בהצלחה"
            if plan.get("draft_schedule_ids"):
                receipt = "הסידור הוחזר לטיוטה והתוכנית הוחלה בהצלחה"
            if kind == "retire":
                receipt = "%s הוצא/ה מהסגל הפעיל. פונו %d משמרות עתידיות; ההיסטוריה נשמרה." % (plan["employee"], len(plan["operations"]))
            elif plan.get("coverage") and not plan["coverage"]["complete"]:
                receipt += ". נותרו %d משמרות שדורשות טיפול." % sum(not row["complete"] for row in plan["coverage"]["slots"])
            payload["receipt"] = {"schedule_id": schedule_id, "starts_on": plan.get("starts_on") or "", "message": receipt}
            self._repo.mark_chat_applied(chat_id, message_id, payload)
            if confirmation:
                self._repo.record_chat_confirmation(chat_id, confirmation["content"],
                                                    confirmation["request_id"], payload["receipt"])
        return self._repo.get_chat(team_id, manager_id, chat_id)

    def _commit_generation(self, team_id, plan, agent_reason):
        generated = plan["generated"]
        schedule_id = plan["schedule_id"]
        if not schedule_id:
            schedule = self._repo.create_schedule(team_id, plan.get("period_starts_on") or plan["starts_on"],
                                                  plan.get("period_ends_on") or plan["ends_on"])
            schedule_id = schedule["id"]
            self._repo.replace_slots(schedule_id, team_id, plan.get("creation_slots") or generated["slots"])
        schedule = self._repo.get_schedule(schedule_id, team_id)
        slots = {(row["shift_name"], iso(row["slot_date"])): row["id"] for row in schedule["slots"]}
        desired = {(row["employee"], row["shift"], iso(row["date"])): row for row in generated["assignments"]}
        first, last = plan["starts_on"], plan["ends_on"]
        existing = {(row["employee"], row["shift"], iso(row["date"])): row for row in schedule["assignments"]
                    if first <= iso(row["date"]) <= last}
        for key, row in existing.items():
            if key not in desired:
                self._repo.remove_assignment(row["id"], team_id)
        for key, row in desired.items():
            if key not in existing:
                self._repo.add_assignment(schedule_id, team_id, slots[(key[1], key[2])],
                                          key[0], row.get("reason") or agent_reason)
        return schedule_id
