"""Build and validate manager-chat plans without writing them."""

from app.bl.changes.proposal import build_proposal
from app.bl.chat_constraints import affected_periods, constraint_impact, normalize_constraints
from app.bl.chat_contract import (
    NeedsManager, RejectedPlan, add_coverage, audit_plan, changed_rows,
    draft_schedule_ids, fingerprint, whole_day_request,
)
from app.bl.chat_generation import prepare_generation
from app.bl.chat_lifecycle import (
    prepare_blank, prepare_profile, prepare_retirement, prepare_structure,
)
from app.bl.chat_management import prepare_management
from app.bl.shared import warning_key
from app.bl.profile_service import ProfileService
from app.bl.schedule_service.generation.history import AssignmentHistory
from app.bl.scheduler import Scheduler
from app.bl.shared import iso
from app.bl.simulate.hypothetical import schedule_rows
from app.bl.tools import ScheduleTools


class ChatPlanBuilder:
    def __init__(self, repository, llm, context, profiles=None):
        self._repo = repository
        self._context = context
        self._profiles = profiles or ProfileService(repository)
        self._scheduler = Scheduler(llm)
        self._history = AssignmentHistory(repository)
        self._tools = ScheduleTools(repository)

    def prepare(self, team_id, turn, focused_id, request, choices=()):
        kind = turn.get("kind") or "answer"
        self._validate_kind(kind, turn)
        if turn.get("needs_input") or kind == "answer":
            return None
        schedule_id = self._schedule_id(team_id, kind, turn, focused_id)
        state = self._context.snapshot(team_id, schedule_id)
        schedule, profile = state["schedule"] or {}, state["profile"]
        if kind == "changes" and whole_day_request(request, profile):
            raise RejectedPlan(
                "בקשת שיבוץ ליום שלם דורשת kind=generate ובדיקת כל המשמרות ביום; "
                "אין להחזיר רק שיבוץ בוקר"
            )
        plan = self._new_plan(kind, schedule_id, turn, request, state, schedule)
        prepared = self._special_plan(
            team_id, kind, turn, plan, state, schedule, profile, request,
        )
        if prepared is not None:
            return prepared
        if kind == "profile":
            prepare_profile(self._profiles, team_id, turn, plan, profile)
        elif kind == "generate":
            prepare_generation(
                self._repo, self._scheduler, self._history,
                team_id, turn, plan, state,
            )
        elif kind == "changes":
            self._changes_plan(
                team_id, turn, plan, state, schedule, profile,
                schedule_id, request, choices,
            )
            if not plan["operations"] and not plan["constraints"]:
                return None
        elif kind == "clear":
            plan["operations"] = [
                dict(
                    action="remove", employee=row["employee"],
                    date=iso(row["date"]), shift=row["shift"],
                    reason=plan["agent_reason"],
                )
                for row in schedule.get("assignments") or []
            ]
        elif kind == "publish":
            plan["warnings"] = self._context.audit_rows(
                team_id, schedule.get("assignments") or [], schedule,
            )
        elif kind != "unpublish":
            raise RejectedPlan("הפעולה אינה נתמכת")
        plan["draft_schedule_ids"] = draft_schedule_ids(plan, state)
        return plan

    @staticmethod
    def _validate_kind(kind, turn):
        from app.bl.chat_contract import confirmation_question

        if kind == "answer" and confirmation_question(turn):
            raise RejectedPlan(
                "אין לבקש אישור בלי תוכנית שמורה. לבקשת שינוי יש להכין תוכנית מלאה; "
                "להתייעצות יש לענות בלי לבקש אישור ביצוע"
            )
        if turn.get("needs_reason"):
            raise RejectedPlan(
                "אין צורך לבקש סיבה. הוראת המנהל היא הסיבה; "
                "יש להכין את התוכנית או לשאול רק על יעד חסר"
            )
        mismatched = (
            (kind != "changes" and (turn.get("operations") or turn.get("constraints")))
            or (kind not in ("profile", "restructure") and turn.get("profile_patch_json"))
            or (kind not in ("generate", "restructure") and turn.get("required_assignments"))
            or (kind != "manage" and turn.get("management_operations"))
            or turn.get("profile_operations")
        )
        if mismatched:
            raise RejectedPlan(
                "סוג התשובה אינו תואם לפעולות. הוראת שיבוץ דורשת kind=changes; "
                "התייעצות דורשת kind=answer בלי פעולות; עריכת צוות דורשת "
                "kind=profile ו-profile_patch_json"
            )

    def _schedule_id(self, team_id, kind, turn, focused_id):
        if kind in ("manage", "blank"):
            return ""
        if kind != "generate":
            return turn.get("schedule_id") or focused_id
        first, last = turn.get("starts_on") or "", turn.get("ends_on") or ""
        periods = self._repo.list_schedules(team_id)
        exact = next((
            period["id"] for period in periods
            if iso(period["starts_on"]) == first and iso(period["ends_on"]) == last
        ), "")
        return exact or next((
            period["id"] for period in periods
            if first and last
            and iso(period["starts_on"]) <= first
            and last <= iso(period["ends_on"])
        ), "")

    @staticmethod
    def _new_plan(kind, schedule_id, turn, request, state, schedule):
        plan = {
            "kind": kind, "schedule_id": schedule_id,
            "agent_reason": (turn.get("agent_reason") or turn.get("reply") or "").strip(),
            "reason": (turn.get("stated_reason") or request).strip(),
            "snapshot": fingerprint(state), "operations": [], "constraints": [],
            "warnings": [], "exceptions": (turn.get("exceptions") or [])[:20],
        }
        if schedule and kind != "profile":
            plan.update(
                starts_on=iso(schedule["starts_on"]),
                ends_on=iso(schedule["ends_on"]),
            )
        return plan

    def _special_plan(self, team_id, kind, turn, plan, state, schedule, profile, request):
        if kind == "manage":
            state["management"] = prepare_management(
                self._repo, team_id, turn, plan, state, request,
            )
            plan["snapshot"] = fingerprint(state)
            return plan
        if kind == "blank":
            return prepare_blank(turn, plan, state, profile)
        if kind == "delete_period":
            if not schedule:
                raise RejectedPlan("בחרו סידור קיים למחיקה")
            if schedule.get("status") == "published":
                raise RejectedPlan("הסידור מפורסם. יש להחזיר אותו לטיוטה לפני מחיקה")
            if (schedule.get("generation") or {}).get("status") in ("pending", "queued", "running"):
                raise RejectedPlan("לא ניתן למחוק סידור בזמן בנייה")
            plan["deleted_assignments"] = len(schedule.get("assignments") or [])
            return plan
        if kind == "retire":
            periods = prepare_retirement(
                self._repo, self._profiles, team_id, turn, plan, state,
            )
            state = dict(state, future_schedules=periods)
            plan["snapshot"] = fingerprint(state)
            plan["draft_schedule_ids"] = draft_schedule_ids(plan, state)
            return plan
        if kind == "restructure":
            prepare_structure(
                self._profiles, self._scheduler, team_id, turn, plan, state,
                self._history.before(team_id, iso(schedule["starts_on"])), audit_plan,
            )
            add_coverage(plan, plan["updated_profile"])
            plan["draft_schedule_ids"] = draft_schedule_ids(plan, state)
            return plan
        return None

    def _changes_plan(
        self, team_id, turn, plan, state, schedule, profile,
        schedule_id, request, choices,
    ):
        if not schedule and turn.get("operations"):
            raise RejectedPlan("אין סידור בשבוע הזה. אפשר לבקש לבנות אותו קודם")
        people = {row["name"]: row for row in profile.get("employees") or []}
        for row in turn.get("operations") or []:
            person = people.get(row.get("employee"), {})
            if row.get("action") == "assign" and person.get("inactive_from") \
                    and (row.get("date") or "") >= person["inactive_from"]:
                raise RejectedPlan("העובד סיים את העבודה לפני המשמרת. יש לבחור מחליף פעיל")
        self._require_selected_replacements(
            team_id, turn, state, profile, schedule_id, request, choices,
        )
        proposal = build_proposal(turn, profile, schedule, plan["reason"])
        if proposal["needs_input"] or proposal["needs_reason"]:
            raise NeedsManager(proposal["reply"] or "נדרשים פרטים נוספים לפני שינוי")
        if len(proposal["operations"]) != len(turn.get("operations") or []):
            raise RejectedPlan("חלק מהשינויים לא תואמים לסידור. יש לבקש תוכנית מעודכנת")
        plan["operations"] = proposal["operations"]
        plan["constraints"] = normalize_constraints(
            turn.get("constraints") or [], profile, state["availability"],
        )
        rows = changed_rows(schedule, plan["operations"]) if schedule else []
        names = {person["name"] for person in profile.get("employees") or []}
        if any(row["employee"] not in names for row in rows):
            raise RejectedPlan("התוכנית מכילה עובד שאינו נמצא בצוות")
        self._audit_changes(
            team_id, plan, state, schedule, profile, schedule_id, rows,
        )

    def _require_selected_replacements(
        self, team_id, turn, state, profile, schedule_id, request, choices,
    ):
        constraints = turn.get("constraints") or []
        if not any(
            row.get("action") != "remove" and not row.get("available", False)
            for row in constraints
        ):
            return
        selections = "\n".join(list(choices) + [request])
        assignments = [
            row for row in turn.get("operations") or [] if row.get("action") == "assign"
        ]
        unselected = [
            row for row in assignments
            if row.get("employee") and row["employee"] not in selections
        ]
        if not unselected:
            return
        candidates = []
        for row in unselected:
            leaving = next((
                item.get("employee", "") for item in turn.get("operations") or []
                if item.get("action") == "remove"
                and item.get("shift") == row.get("shift")
                and item.get("date") == row.get("date")
            ), "")
            candidates.append(self._tools.run(team_id, "find_replacements", {
                "schedule_id": schedule_id, "employee": leaving,
                "shift_name": row.get("shift"), "slot_date": row.get("date"),
            }))
        if any(result.get("candidates") for result in candidates):
            prompt = "בדקתי מועמדים להחלפה. בחרו מי יחליף בכל משמרת כדי שאכין תוכנית מלאה לאישור."
        else:
            prompt = (
                "לא נמצאו מחליפים שעומדים בכל הכללים. אפשר לשנות את היקף המשמרת "
                "או להוסיף תגבור. איך תרצו לפתור את החוסר?"
            )
        raise NeedsManager(
            prompt, candidates,
            dict(
                request=request,
                constraints=normalize_constraints(
                    constraints, profile, state["availability"],
                ),
            ),
        )

    def _audit_changes(self, team_id, plan, state, schedule, profile, schedule_id, rows):
        if schedule:
            existing = {
                warning_key(row) for row in audit_plan(
                    profile, schedule, schedule_rows(schedule),
                    state["availability"], [],
                )
            }
            plan["warnings"] = [
                row for row in audit_plan(
                    profile, schedule, rows, state["availability"], plan["constraints"],
                )
                if warning_key(row) not in existing
            ]
        if not plan["constraints"]:
            return
        periods = affected_periods(self._repo, team_id, plan["constraints"])
        state["constraint_periods"] = periods
        projected = [
            dict(period, assignments=rows) if period["id"] == schedule_id else period
            for period in periods
        ]
        plan["constraint_feedback"], impact = constraint_impact(
            profile, projected, state["availability"], plan["constraints"],
        )
        known = {warning_key(row) for row in plan["warnings"]}
        plan["warnings"].extend(
            row for row in impact if warning_key(row) not in known
        )
        plan["snapshot"] = fingerprint(state)
