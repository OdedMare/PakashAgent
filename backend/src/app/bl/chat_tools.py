"""Read-only tools and conversation context for manager chat."""

from app.bl import intent as intent_reader
from app.bl.audit import shift_stats
from app.bl.changes.proposal import build_proposal
from app.bl.chat_constraints import constraints_report, normalize_constraints
from app.bl.chat_contract import RejectedPlan, audit_plan, changed_rows, plan_for_model
from app.bl.planner.fallback_answers import FallbackAnswers
from app.bl.shared import warning_key
from app.bl.simulate.hypothetical import schedule_rows
from app.bl.tools import ScheduleTools, TOOL_DESCRIPTIONS
from app.bl.tools.schedule_tools import _invalid_date_argument
from app.bl.shared import iso
from app.common.errors import AgentError
from app.common.time_context import israel_today

_FULL_RESULTS = 2
_EXTRA_DESCRIPTIONS = {
    "list_periods": "כל הסידורים השמורים של הצוות ותאריכיהם",
    "workload_report": "השוואת שעות, מספר משמרות וכוננויות בכל טווח תאריכים",
    "change_history": "מה השתנה בסידורים ומדוע",
    "simulate_changes": "בדיקת מה יקרה אם מבצעים כמה שינויים יחד, כולל כיסוי ועומסים; ללא שמירה",
    "constraints_report": "אילוצים שמורים וקבועים, שעות ועדיפות, בקשות שממתינות לאישור, וכיבוד או התנגשות מול כל הסידורים בטווח",
    "request_inbox": "בקשות אילוץ והחלפות של הצוות, עם מזהים וסטטוסים אמיתיים להחלטת מנהל",
    "preference_list": "כל ההעדפות השמורות של הצוות: פעילות, מוצעות ומושבתות, עם מזהים לעריכה",
}


class ManagerChatTools:
    def __init__(self, repository, schedules, context):
        self._repo = repository
        self._schedules = schedules
        self._context = context
        self._tools = ScheduleTools(repository)
        self._fallback = FallbackAnswers(self._tools)

    @property
    def descriptions(self):
        return dict(TOOL_DESCRIPTIONS, **_EXTRA_DESCRIPTIONS)

    def replacement_lookup(self, team_id, request, context, schedule, profile):
        """Answer one clear candidate lookup without a model round."""
        employees = [row.get("name") or "" for row in profile.get("employees") or []]
        mentioned = {name for name in employees if name and name in request}
        if len(mentioned) != 1:
            return None
        shifts = [row.get("name") or "" for row in profile.get("shifts") or []]
        read = intent_reader.read(
            request, employees, shifts,
            today=israel_today().isoformat(), period=schedule,
        )
        if read["intent"] not in (
            intent_reader.INTENT_REPLACEMENTS, intent_reader.INTENT_ABSENCE,
        ):
            return None
        if not read["date"]:
            read = dict(read, date=context.get("focus_date") or "")
        if not read["employee"] or not read["date"]:
            return None
        reply, steps, results, _ = self._fallback.replacements(team_id, read)
        candidates = [row for row in results if row.get("tool") == "find_replacements"]
        if not candidates or not any(row.get("candidates") for row in candidates):
            return None
        output = {"steps": steps, "results": results, "question": None}
        if read["intent"] == intent_reader.INTENT_ABSENCE:
            output["task"] = {
                "request": request,
                "constraints": normalize_constraints([{
                    "employee": read["employee"], "date": read["date"],
                    "shift": "", "available": False, "reason": request,
                }], profile, self._repo.availability(team_id)),
            }
        return reply, output

    @staticmethod
    def focus_arguments(name, arguments, schedule_id, context):
        """Aim a dateless read at the week on screen."""
        has_date = arguments.get("day") or arguments.get("slot_date")
        if (name not in TOOL_DESCRIPTIONS and name != "simulate_changes") \
                or arguments.get("schedule_id") or has_date:
            return arguments
        if schedule_id:
            return dict(arguments, schedule_id=schedule_id)
        needs_week = name in (
            "read_period", "employee_state", "coverage_gaps",
            "publish_readiness", "simulate_changes",
        )
        if needs_week:
            if not context.get("visible_week"):
                return None
            return dict(arguments, day=context["visible_week"])
        return arguments

    @staticmethod
    def conversation(chat, working_id):
        """Recent turns in full, older plans and checks as summaries."""
        all_rows = [row for row in chat["messages"] if row["id"] != working_id]
        retained = set(range(max(0, len(all_rows) - 32), len(all_rows)))
        for key in ("plan", "question", "results", "task"):
            anchor = next((
                index for index in range(len(all_rows) - 1, -1, -1)
                if (all_rows[index].get("payload") or {}).get(key)
            ), None)
            if anchor is not None:
                retained.update(index for index in (anchor - 1, anchor, anchor + 1)
                                if 0 <= index < len(all_rows))
        rows = [all_rows[index] for index in sorted(retained)]
        planned = [i for i, row in enumerate(rows) if (row.get("payload") or {}).get("plan")]
        checked = [i for i, row in enumerate(rows) if (row.get("payload") or {}).get("results")]
        latest_plan = planned[-1] if planned else -1
        recent_results = set(checked[-_FULL_RESULTS:])
        result = []
        for index, row in enumerate(rows):
            payload = row.get("payload") or {}
            context = {}
            for key in ("task", "question"):
                if payload.get(key):
                    context[key] = payload[key]
            if index in recent_results:
                context["results"] = payload["results"]
            elif payload.get("steps"):
                context["checked"] = sorted({step["tool"] for step in payload["steps"]})
            if payload.get("plan"):
                context["plan"] = plan_for_model(payload["plan"], index == latest_plan)
            result.append({
                "role": row["role"], "content": row["content"],
                "status": row["status"], "context": context,
            })
        return result

    def run(self, team_id, name, arguments, focused_id):
        invalid = _invalid_date_argument(arguments)
        if invalid:
            return {"tool": name, "ok": False, "error": "נדרש תאריך מוחלט עבור " + invalid}
        readers = {
            "list_periods": lambda: {"periods": self._repo.list_schedules(team_id)},
            "constraints_report": lambda: constraints_report(
                self._repo, team_id, arguments, focused_id=focused_id,
            ),
            "request_inbox": lambda: {
                "constraint_requests": self._repo.list_requests(team_id),
                "swap_requests": self._repo.list_swaps(team_id),
            },
            "preference_list": lambda: {"preferences": self._repo.preferences(team_id)},
            "change_history": lambda: {"changes": self._repo.change_log(team_id, limit=60)},
            "workload_report": lambda: self._workload(team_id, arguments, focused_id),
        }
        if name in readers:
            return dict(readers[name](), tool=name, ok=True)
        if name == "simulate_changes":
            return self._simulate(team_id, name, arguments, focused_id)
        if name == "find_replacements":
            arguments = dict(arguments, include_exceptions=False)
        return self._tools.run(team_id, name, arguments)

    def _simulate(self, team_id, name, arguments, focused_id):
        period = self._tools.run(team_id, "read_period", {
            key: arguments[key]
            for key in ("schedule_id", "day") if arguments.get(key)
        }) if arguments.get("schedule_id") or arguments.get("day") else None
        schedule_id = ((period or {}).get("schedule") or {}).get("id") or focused_id
        if (period and not period.get("found")) or not schedule_id:
            return {"tool": name, "ok": False, "error": "יש לבחור סידור קיים או לציין את השבוע"}
        operations = arguments.get("operations") or []
        schedule = self._repo.get_schedule(schedule_id, team_id)
        profile = self._context.profile(team_id)
        proposal = build_proposal(
            dict(operations=operations), profile, schedule, "בדיקת תרחיש",
        )
        if proposal["needs_input"] or len(proposal["operations"]) != len(operations):
            raise RejectedPlan(
                proposal["reply"] or "יש לציין עובדים, משמרות ותאריכים מוכרים לכל השינויים"
            )
        rows = changed_rows(schedule, proposal["operations"])
        names = {person["name"] for person in profile.get("employees") or []}
        if any(row["employee"] not in names for row in rows):
            raise RejectedPlan("יש להשתמש בשמות העובדים המלאים מרשימת הצוות")
        result = self._schedules.simulate(team_id, proposal["operations"], schedule_id)
        availability = self._repo.availability(team_id)
        before = {
            warning_key(row): row for row in audit_plan(
                profile, schedule, schedule_rows(schedule), availability, [],
            )
        }
        after = audit_plan(profile, schedule, rows, availability, [])
        after_keys = {warning_key(row) for row in after}
        return dict(
            result, tool=name, ok=True, warnings_after=after,
            introduced=[row for row in after if warning_key(row) not in before],
            resolved=[row for key, row in before.items() if key not in after_keys],
        )

    def _workload(self, team_id, arguments, focused_id):
        profile = self._context.profile(team_id)
        first = arguments.get("starts_on") or ""
        last = arguments.get("ends_on") or ""
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
        return {
            "found": True, "starts_on": first, "ends_on": last,
            "periods": included, "basis": "scheduled",
            "stats": shift_stats(
                assignments, profile.get("shifts") or [],
                profile.get("employees") or [], profile=profile,
            ),
        }
