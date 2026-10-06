"""Small, deterministic conversation contracts shared by proposals and approvals."""

import datetime
import re

from app.bl.audit import audit
from app.bl.placement.values import is_eligible
from app.bl.scheduler.availability import effective_availability
from app.bl.audit.staffing_rules import required_headcount, seat_counts
from app.bl.tools.values import iso
from app.bl.intent.dates import date_in, explicit_date, parse
from app.common.time_context.time_context import israel_today
from app.common.errors.errors import AgentError

GAP_CODES = frozenset({"unfilled", "missing_role", "missing_commander"})


class RejectedPlan(AgentError):
    """A malformed proposal the model can repair."""


class NeedsManager(AgentError):
    """An essential detail that cannot be inferred."""

    def __init__(self, message, results=None, task=None):
        super().__init__(message)
        self.results = results or []
        self.task = task


def approval_text(content):
    normalized = re.sub(r"[\s,.!؟?]+", " ", content.strip()).strip()
    return normalized in {
        "כן", "כן תעשה", "כן תעשי", "כן תבצע", "תבצע", "תעשי", "מאשר",
        "מאשרת", "מאשר את התוכנית", "מאשרת את התוכנית", "החל שינויים",
        "אישור", "אני מאשר", "אני מאשרת", "כן מאשר", "כן מאשרת",
        "אני מאשר את התוכנית", "אני מאשרת את התוכנית", "מאושר",
        "תאשר", "תאשרי", "תאשר את התוכנית", "תאשרי את התוכנית",
    }


def exception_warnings(plan):
    return [row for row in plan.get("warnings") or []
            if row.get("severity", "warning") == "warning" and row.get("code") not in GAP_CODES]


def confirmation_question(turn):
    asked = turn.get("question") or {}
    content = asked.get("question", "") if isinstance(asked, dict) else str(asked)
    return bool(re.search(r"\b(?:מאשר|מאשרת|תאשר|תאשרי|לאשר|אישור)\b", content))


def whole_day_request(content, profile):
    imperative = re.match(r"^(?:בבקשה\s+)?(?:תשבץ|תשבצי|שבץ|שבצי)\b", content.strip())
    day = re.search(r"היום|מחר|יום\s|את\s+(?:ראשון|שני|שלישי|רביעי|חמישי|שישי|שבת)|כל המשמרות", content)
    all_shifts = "כל המשמרות" in content or "כל היום" in content
    specific_shift = any(row.get("name") and row["name"] in content for row in profile.get("shifts") or [])
    return bool(imperative and day and (all_shifts or not specific_shift))


def normalize_day_turn(turn, request, context, profile):
    """A clear whole-day instruction cannot degrade into one shift or a promise.

    Reuse the existing date reader; the scheduler still chooses and verifies
    employees. Mixed edits, consultations and genuine questions stay with the model.
    """
    if not whole_day_request(request, profile) or turn.get("kind") not in ("answer", "changes", "generate") \
            or ((turn.get("needs_input") or turn.get("question")) and not confirmation_question(turn)) \
            or turn.get("constraints") \
            or turn.get("profile_patch_json"):
        return turn
    if len(re.findall(r"\d{4}-\d{2}-\d{2}", request)) > 1:
        return turn
    today = israel_today()
    explicit = explicit_date(request, today)
    # "next Monday" needs the model's temporal interpretation rather than
    # the date reader's current-period weekday lookup.
    if not explicit and ("הבא" in request or "הבאה" in request):
        return turn
    first = parse(context.get("visible_week"))
    period = dict(starts_on=first.isoformat(), ends_on=(first + datetime.timedelta(days=6)).isoformat()) if first else None
    focused = context.get("focus_date") or ""
    target = explicit or (focused if focused and ("היום" in request or "יום הזה" in request) else "") \
        or date_in(request, today.isoformat(), period)
    if not explicit and not focused and not re.search(r"היום|מחר|אתמול", request) \
            and turn.get("copy_from_date") and turn.get("starts_on") == turn.get("ends_on"):
        source, proposed = parse(turn["copy_from_date"]), parse(turn.get("starts_on"))
        if source and proposed and proposed == source + datetime.timedelta(days=7):
            target = proposed.isoformat()
    if not target:
        raise NeedsManager("לאיזה תאריך לשבץ את כל המשמרות?")
    copy = (datetime.date.fromisoformat(target) - datetime.timedelta(days=7)).isoformat() \
        if "שבוע שעבר" in request else turn.get("copy_from_date") or ""
    return dict(turn, kind="generate", starts_on=target, ends_on=target,
                needs_input=False, question=None,
                operations=[], constraints=[], profile_operations=[],
                instructions=(turn.get("instructions") or "") + "\n" + request,
                replace_existing=bool(copy or "מחדש" in request or turn.get("replace_existing")),
                copy_from_date=copy, reply=turn.get("reply") or "הכנתי תוכנית ליום שנבחר לאישור")


def normalize_week_turn(turn, request, context, profile):
    """Bind a clear whole-week instruction to seven dates before scheduling."""
    from app.dal.repository.schedules import week_bounds

    command = re.match(r"^(?:בבקשה\s+)?(?:אני רוצה ש)?(?:תבנה|תבני|בנה|בני|תכין|תכיני|הכן|הכיני|תייצר|תייצרי|צור|צרי|תיצור|תצרי|תשבץ|תשבצי|שבץ|שבצי|תמלא|תמלאי)\b", request.strip())
    if not command or not re.search(r"\b[לבה]?שבוע\b", request) or "שבוע שעבר" in request \
            or whole_day_request(request, profile) \
            or re.search(r"\b(?:ראשון|שני|שלישי|רביעי|חמישי|שישי|שבת)\b", request) \
            or turn.get("kind") not in ("answer", "changes", "generate") \
            or ((turn.get("needs_input") or turn.get("question")) and not confirmation_question(turn)) \
            or turn.get("constraints") \
            or turn.get("profile_patch_json") \
            or any(row.get("name") and row["name"] in request
                   for row in (profile.get("shifts") or []) + (profile.get("employees") or [])):
        return turn
    if len(re.findall(r"\d{4}-\d{2}-\d{2}", request)) > 1:
        return turn
    today = israel_today()
    explicit = explicit_date(request, today)
    if explicit:
        anchor = parse(explicit)
    elif "הבא" in request or "הקרוב" in request:
        anchor = parse(week_bounds(today)[0]) + datetime.timedelta(days=7)
    else:
        anchor = parse(context.get("visible_week")) or today
    first, last = week_bounds(anchor)
    return dict(turn, kind="generate", starts_on=first, ends_on=last, schedule_id="",
                needs_input=False, question=None,
                operations=[], constraints=[], profile_operations=[], copy_from_date="",
                instructions=(turn.get("instructions") or "") + "\n" + request,
                replace_existing=bool("מחדש" in request or turn.get("replace_existing")),
                reply="הכנתי תוכנית לשבוע %s – %s לאישור" % (first, last))


def draft_schedule_ids(plan, state):
    """Only periods whose saved assignments/grid will change need a draft."""
    if plan["kind"] == "retire":
        affected = {row["schedule_id"] for row in plan["affected_schedules"]}
        return [row["id"] for row in state["future_schedules"]
                if row["id"] in affected and row["status"] == "published"]
    schedule = state.get("schedule") or {}
    if schedule.get("status") != "published":
        return []
    changed = bool(plan.get("operations"))
    if plan["kind"] in ("generate", "restructure"):
        keys = lambda rows: {(row["employee"], row["shift"], iso(row["date"])) for row in rows}
        saved = [row for row in schedule.get("assignments") or []
                 if plan["starts_on"] <= iso(row["date"]) <= plan["ends_on"]]
        changed = keys(saved) != keys(plan["generated"]["assignments"])
        if plan["kind"] == "restructure":
            changed = changed or plan["updated_profile"] != state["profile"]
    return [schedule["id"]] if changed else []


def coverage_preview(profile, slots, assignments, warnings):
    """Every requested slot, even when the model returned no placements for it."""
    counts = seat_counts(assignments, profile.get("employees") or [], profile)
    result = []
    for slot in slots:
        date, shift = iso(slot["slot_date"]), slot["shift_name"]
        required = required_headcount(profile.get("shifts") or [], shift,
                                      datetime.date.fromisoformat(date), slots)
        problems = [row["message"] for row in warnings
                    if iso(row.get("date")) == date and row.get("shift") == shift]
        assigned = counts.get((date, shift), 0)
        complete = required is not None and assigned >= required and not problems
        result.append(dict(date=date, shift=shift, required=required, assigned=assigned,
                           complete=complete, problems=problems,
                           start_time=slot.get("start_time") or "",
                           end_time=slot.get("end_time") or ""))
    return dict(complete=bool(result) and all(row["complete"] for row in result), slots=result)


def add_coverage(plan, profile):
    generated = plan["generated"]
    plan["coverage"] = coverage_preview(profile, generated["slots"],
                                        generated["assignments"], plan["warnings"])


def audit_plan(profile, schedule, rows, availability, constraints):
    facts = {(row["employee"], iso(row["constraint_date"]), row.get("shift_name") or ""):
             dict(row, date=iso(row["constraint_date"]), shift=row.get("shift_name") or "")
             for row in availability}
    facts.update({(row["employee"], row["date"], row.get("shift") or ""): row
                  for row in constraints})
    warnings = audit(
        rows, profile.get("shifts") or [], profile.get("employees") or [],
        effective_availability(profile, list(facts.values()), iso(schedule["starts_on"]),
                               iso(schedule["ends_on"])),
        profile, schedule.get("slots") or [],
    )
    for row in rows:
        if not is_eligible(profile, row["employee"], row["shift"], iso(row["date"])):
            warnings.append(dict(code="ineligible", severity="warning", employee=row["employee"],
                                 date=iso(row["date"]), shift=row["shift"], details={},
                                 message="%s לא מוגדר/ת למשמרת %s בפרופיל הצוות" %
                                 (row["employee"], row["shift"])))
    return warnings
