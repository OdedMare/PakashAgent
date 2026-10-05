"""Conversation orchestration over the existing model, tools and services.

No model call has write access. A stored plan is validated and applied only
under a separate, private, atomic approval. Background replies are read-only.
"""

import datetime
import hashlib
import json
import logging

from app.bl.audit import audit, shift_stats
from app.bl.changes.agent import _closures_for_model, _schedule_for_model
from app.bl.changes.proposal import build_proposal
from app.bl.changes.values import json_default
from app.bl.chat_schema import CHAT_SCHEMA, PROFILE_SECTIONS
from app.bl.planner.shaping import question
from app.bl.profile_service import ProfileService
from app.bl.prompts import load
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.generation.history import AssignmentHistory
from app.bl.schedule_service.generation.pins import model_assignment
from app.bl.schedule_service.operations import OperationApplier
from app.bl.scheduler import Scheduler
from app.bl.scheduler.availability import effective_availability
from app.bl.simulate.hypothetical import Hypothetical, schedule_rows
from app.bl.tools import ScheduleTools, TOOL_DESCRIPTIONS
from app.bl.tools.schedule_tools import _invalid_date_argument
from app.bl.tools.values import iso
from app.common.errors.errors import AgentError, AppError, ConflictError
from app.common.time_context.time_context import agent_time_context

_log = logging.getLogger("pakash.chat")
_EXTRA_TOOLS = {
    "list_periods": "כל הסידורים השמורים של הצוות ותאריכיהם",
    "workload_report": "השוואת שעות, מספר משמרות וכוננויות בכל טווח תאריכים",
    "change_history": "מה השתנה בסידורים ומדוע",
}
_ROUNDS = 7      # model calls per turn; the last one may not request tools
_REPAIRS = 2     # times a rejected plan is handed back to the model to fix
_MAX_CALLS = 4   # tool calls the model may request per round
_FULL_RESULTS = 2  # earlier turns whose tool results the model re-reads in full


class _Rejected(AgentError):
    """A plan the code refused, which the model can revise in the same turn."""


class _NeedsManager(AgentError):
    """Only the manager can supply what is missing (D8): ask, do not repair."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)


def _iso_or_blank(value):
    """A focus day the browser sent, or nothing; never a malformed date."""
    try:
        return datetime.date.fromisoformat(value or "").isoformat()
    except ValueError:
        return ""


def _plan_for_model(plan, whole):
    """A stored plan as the model reads it back: whole, or as a summary."""
    # The snapshot hash and the generated slot grid mean nothing to the model.
    shown = {key: value for key, value in plan.items() if key != "snapshot"}
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
        return self._repo.start_chat_turn(
            team_id, manager_id, chat_id, request["content"].strip(),
            request["request_id"], {
                "schedule_id": request.get("schedule_id") or "",
                "visible_week": request.get("visible_week") or "",
                "focus_date": _iso_or_blank(request.get("focus_date")),
            },
        )

    def reply(self, team_id, manager_id, chat_id, message_id):
        try:
            chat = self._repo.get_chat(team_id, manager_id, chat_id)
            message = next(row for row in chat["messages"] if row["id"] == message_id)
            if message["status"] != "working":
                return
            context = message["payload"]
            schedule_id = context.get("schedule_id") or ""
            schedule = self._repo.get_schedule(schedule_id, team_id) if schedule_id else None
            profile = self._context.profile(team_id)
            payload = {
                "clock": agent_time_context(), "profile": profile,
                "profile_sections": PROFILE_SECTIONS,
                "focused_schedule_id": schedule_id,
                "visible_week": context.get("visible_week") or "",
                "focused_date": context.get("focus_date") or "",
                "schedule": _schedule_for_model(schedule or {}),
                "closures": _closures_for_model(profile, schedule or {}),
                "availability": self._repo.availability(team_id),
                "preferences": self._context.active_preferences(team_id),
                "history": self._repo.change_log(team_id, limit=12),
                "conversation": self._conversation(chat, message_id),
                "tools": dict(TOOL_DESCRIPTIONS, **_EXTRA_TOOLS),
            }
            results, steps = [], []
            plan, asked, repairs = None, "", 0
            for round_ in range(_ROUNDS):
                final = round_ == _ROUNDS - 1
                turn = self._llm.complete_json(
                    load("manager_chat"), _json(dict(payload, results=results, final_round=final)),
                    schema=CHAT_SCHEMA, flow="planner",
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
                    plan = self._prepare_plan(team_id, turn, schedule_id)
                except _NeedsManager as exc:
                    asked = str(exc)
                except _Rejected as exc:
                    if final or repairs >= _REPAIRS:
                        raise
                    # The code refused the plan; the model sees why and revises it.
                    repairs += 1
                    results.append({"tool": "plan_check", "ok": False, "error": str(exc)})
                    steps.append({"tool": "plan_check", "ok": False})
                    continue
                break
            output = {"steps": steps, "results": results, "question": question(turn.get("question"))}
            if plan:
                output["plan"] = plan
            reply = asked or (turn.get("reply") or "").strip()
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
            self._repo.finish_chat_turn(chat_id, message_id, content, "error", {})

    @staticmethod
    def _focus_arguments(name, arguments, schedule_id, context):
        """Aim a dateless read at the week on screen; None when nothing is."""
        if name not in TOOL_DESCRIPTIONS or arguments.get("schedule_id") \
                or arguments.get("day") or arguments.get("slot_date"):
            return arguments
        if schedule_id:
            return dict(arguments, schedule_id=schedule_id)
        if name in ("read_period", "employee_state", "coverage_gaps", "publish_readiness"):
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
        rows = [row for row in chat["messages"][-32:] if row["id"] != working_id]
        planned = [index for index, row in enumerate(rows) if (row.get("payload") or {}).get("plan")]
        checked = [index for index, row in enumerate(rows) if (row.get("payload") or {}).get("results")]
        latest_plan = planned[-1] if planned else -1
        recent_results = set(checked[-_FULL_RESULTS:])
        result = []
        for index, row in enumerate(rows):
            item = {"role": row["role"], "content": row["content"], "status": row["status"]}
            payload = row.get("payload") or {}
            context = {}
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
        if name == "find_replacements":
            arguments = dict(arguments, include_exceptions=True)
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
            first, last = iso(periods[0]["starts_on"]), iso(periods[0]["ends_on"])
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

    def _prepare_plan(self, team_id, turn, focused_id):
        kind = turn.get("kind") or "answer"
        if kind == "answer" or turn.get("needs_input") or turn.get("needs_reason"):
            return None
        schedule_id = turn.get("schedule_id") or focused_id
        if kind == "generate" and not turn.get("schedule_id"):
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
        plan = {
            "kind": kind, "schedule_id": schedule_id,
            "agent_reason": (turn.get("agent_reason") or turn.get("reply") or "").strip(),
            "reason": (turn.get("stated_reason") or "").strip(),
            "snapshot": _fingerprint(state), "operations": [], "constraints": [],
            "warnings": [], "exceptions": (turn.get("exceptions") or [])[:20],
        }
        if schedule and kind != "profile":
            plan.update(starts_on=iso(schedule["starts_on"]), ends_on=iso(schedule["ends_on"]))
        if kind == "profile":
            try:
                patch = json.loads(turn.get("profile_patch_json") or "{}")
            except ValueError as exc:
                raise _Rejected("עריכת הפרופיל אינה תקינה. אפשר לנסח שוב") from exc
            if not isinstance(patch, dict) or not patch or set(patch) - set(PROFILE_SECTIONS):
                raise _Rejected("לא זוהה שינוי תקין בפרטי הצוות")
            try:
                updated = self._profiles.preview(team_id, **patch)
            except AppError as exc:
                raise _Rejected(str(exc)) from exc
            plan["profile_patch"] = patch
            plan["profile_before"] = {key: profile.get(key) for key in patch}
            plan["profile_after"] = {key: updated.get(key) for key in patch}
        elif kind == "generate":
            self._prepare_generation(team_id, turn, plan, state)
        else:
            if not schedule and (kind != "changes" or turn.get("operations")):
                raise _Rejected("אין סידור בשבוע הזה. אפשר לבקש לבנות אותו קודם")
            if kind not in ("publish", "unpublish") and schedule.get("status") == "published":
                raise _Rejected("הסידור מפורסם. בקשו להחזיר אותו לטיוטה לפני שינוי")
            if kind == "changes":
                proposal = build_proposal(turn, profile, schedule, plan["reason"])
                if proposal["needs_input"] or proposal["needs_reason"]:
                    raise _NeedsManager(proposal["reply"] or "נדרשים פרטים נוספים לפני שינוי")
                if len(proposal["operations"]) != len(turn.get("operations") or []):
                    raise _Rejected("חלק מהשינויים לא תואמים לסידור. יש לבקש תוכנית מעודכנת")
                plan["operations"] = proposal["operations"]
                plan["constraints"] = self._constraints(turn.get("constraints") or [], profile)
                if not plan["operations"] and not plan["constraints"]:
                    return None
                if not plan["reason"]:
                    raise _NeedsManager("מה הסיבה לשינוי בסידור?")
                rows = self._changed_rows(schedule, plan["operations"]) if schedule else []
                names = {person["name"] for person in profile.get("employees") or []}
                if any(row["employee"] not in names for row in rows):
                    raise _Rejected("התוכנית מכילה עובד שאינו נמצא בצוות")
                if schedule:
                    plan["warnings"] = self._audit_plan(profile, schedule, rows, state["availability"], plan["constraints"])
            elif kind == "clear":
                if not plan["reason"]:
                    raise _NeedsManager("מה הסיבה לפינוי השיבוצים?")
                plan["operations"] = [dict(action="remove", employee=row["employee"],
                                           date=iso(row["date"]), shift=row["shift"],
                                           reason=plan["agent_reason"])
                                      for row in schedule.get("assignments") or []]
            elif kind == "publish":
                plan["warnings"] = self._context.audit_rows(team_id, schedule.get("assignments") or [], schedule)
            elif kind != "unpublish":
                raise _Rejected("הפעולה אינה נתמכת")
        return plan

    def _prepare_generation(self, team_id, turn, plan, state):
        first, last = turn.get("starts_on") or "", turn.get("ends_on") or ""
        try:
            start, end = datetime.date.fromisoformat(first), datetime.date.fromisoformat(last)
        except ValueError as exc:
            raise _Rejected("נדרשים תאריכי התחלה וסיום לבניית הסידור") from exc
        if end < start or (end - start).days > 62:
            raise _Rejected("אפשר לבנות בשיחה תקופה של עד 63 ימים")
        schedule = state["schedule"] or {}
        if not schedule:
            matches = [period for period in state["periods"]
                       if iso(period["starts_on"]) <= last and iso(period["ends_on"]) >= first]
            if matches:
                raise _Rejected("קיים סידור בטווח הזה. יש לבקש למלא או לבנות מחדש את הסידור הקיים")
        elif not (iso(schedule["starts_on"]) <= first and last <= iso(schedule["ends_on"])):
            raise _Rejected("הטווח חורג מהסידור שנבחר. יש לבחור את התקופה המתאימה")
        if schedule.get("status") == "published":
            raise _Rejected("יש להחזיר את הסידור לטיוטה לפני בנייה מחדש")
        # A range inside an existing period (one day, a few days) rebuilds only
        # those dates; every other saved assignment stays as it is.
        partial = bool(schedule) and (iso(schedule["starts_on"]) != first or iso(schedule["ends_on"]) != last)
        saved = schedule.get("assignments") or []
        inside = [row for row in saved if first <= iso(row["date"]) <= last]
        outside = [row for row in saved if not first <= iso(row["date"]) <= last]
        required = [dict(employee=row["employee"], shift=row["shift"], date=iso(row["date"]))
                    for row in inside
                    if not turn.get("replace_existing") or row.get("source") == "manager"]
        plan["preserved_assignments"] = list(required)
        required += [row for row in turn.get("required_assignments") or []
                     if first <= (row.get("date") or "") <= last]
        if partial:
            generated = self._scheduler.generate_span(
                state["profile"], first, last, availability=state["availability"],
                history=self._history.before(team_id, iso(schedule["starts_on"])),
                preferences=state["preferences"], instructions=turn.get("instructions") or "",
                required_assignments=required,
                already_scheduled=[model_assignment(row) for row in outside],
            )
        else:
            generated = self._scheduler.generate(
                state["profile"], first, last, availability=state["availability"],
                history=self._history.before(team_id, first),
                preferences=state["preferences"], instructions=turn.get("instructions") or "",
                required_assignments=required,
            )
        pseudo = dict(schedule, starts_on=iso(schedule["starts_on"]) if partial else first,
                      ends_on=iso(schedule["ends_on"]) if partial else last,
                      slots=schedule.get("slots") or generated["slots"])
        if schedule:
            slots = {(row["shift_name"], iso(row["slot_date"])) for row in schedule["slots"]}
            if any((row["shift"], row["date"]) not in slots for row in generated["assignments"]):
                raise AgentError("סוגי המשמרות השתנו מאז יצירת הסידור. יש לבנות תקופה חדשה")
        plan.update(starts_on=first, ends_on=last, generated=generated,
                    replace_existing=bool(turn.get("replace_existing")))
        context_rows = [dict(employee=row["employee"], shift=row["shift"], date=iso(row["date"]))
                        for row in outside] if partial else []
        plan["warnings"] = self._audit_plan(state["profile"], pseudo,
                                           context_rows + generated["assignments"], state["availability"], [])

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
        return imagined.rows

    def _audit_plan(self, profile, schedule, rows, availability, constraints):
        facts = {(row["employee"], iso(row["constraint_date"]), row.get("shift_name") or ""):
                 dict(row, date=iso(row["constraint_date"]), shift=row.get("shift_name") or "")
                 for row in availability}
        facts.update({(row["employee"], row["date"], row.get("shift") or ""): row
                      for row in constraints})
        return audit(
            rows, profile.get("shifts") or [], profile.get("employees") or [],
            effective_availability(profile, list(facts.values()), iso(schedule["starts_on"]),
                                   iso(schedule["ends_on"])),
            profile, schedule.get("slots") or [],
        )

    def apply(self, team_id, manager_id, chat_id, message_id, accept_exceptions=False):
        with self._repo.chat_approval(team_id, manager_id, chat_id, message_id) as message:
            if message["status"] == "applied":
                return self._repo.get_chat(team_id, manager_id, chat_id)
            payload = message["payload"]
            plan = payload.get("plan") or {}
            state = self._state(team_id, plan.get("schedule_id") or "")
            if _fingerprint(state) != plan.get("snapshot"):
                raise ConflictError("הסידור או כללי הצוות השתנו מאז ההמלצה. בקשו תוכנית מעודכנת")
            if (plan.get("warnings") or plan.get("exceptions")) and not accept_exceptions:
                raise ConflictError("יש לאשר במפורש את החריגות המוצגות בתוכנית")
            reason = plan.get("reason") or message["content"]
            agent_reason = plan.get("agent_reason") or "שינוי שאושר בשיחה"
            conflicts = [row.get("message", "") for row in plan.get("warnings") or []]
            conflicts += plan.get("exceptions") or []
            if conflicts:
                agent_reason += "\nחריגות שאושרו במפורש: " + "; ".join(conflicts)
            kind, schedule_id = plan.get("kind"), plan.get("schedule_id") or ""
            if kind == "profile":
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
            payload["receipt"] = {"schedule_id": schedule_id, "message": "התוכנית הוחלה בהצלחה"}
            self._repo.mark_chat_applied(chat_id, message_id, payload)
        return self._repo.get_chat(team_id, manager_id, chat_id)

    def _commit_generation(self, team_id, plan, agent_reason):
        generated = plan["generated"]
        schedule_id = plan["schedule_id"]
        if not schedule_id:
            schedule = self._repo.create_schedule(team_id, plan["starts_on"], plan["ends_on"])
            schedule_id = schedule["id"]
            self._repo.replace_slots(schedule_id, team_id, generated["slots"])
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
