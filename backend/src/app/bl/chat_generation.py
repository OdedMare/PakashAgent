"""Prepare verified schedule previews without writing a schedule."""

import datetime

from app.bl.chat_contract import RejectedPlan as _Rejected, add_coverage, audit_plan
from app.bl.chat_lifecycle import copied_day
from app.bl.schedule_service.generation.pins import model_assignment
from app.bl.tools.values import iso
from app.bl.scheduler import build_slots
from app.dal.repository.schedules import week_bounds
from app.common.errors.errors import AgentError

def prepare_generation(repository, scheduler, history, team_id, turn, plan, state):
    first, last = turn.get("starts_on") or "", turn.get("ends_on") or ""
    try:
        start, end = datetime.date.fromisoformat(first), datetime.date.fromisoformat(last)
    except ValueError as exc:
        raise _Rejected("נדרשים תאריכי התחלה וסיום לבניית הסידור") from exc
    if end < start or (end - start).days > 62:
        raise _Rejected("אפשר לבנות בשיחה תקופה של עד 63 ימים")
    schedule = state["schedule"] or {}
    if not schedule:
        period_first = week_bounds(start)[0]
        period_last = week_bounds(end)[1]
        matches = [period for period in state["periods"]
                   if iso(period["starts_on"]) <= period_last and iso(period["ends_on"]) >= period_first]
        if matches:
            raise _Rejected("קיים סידור בטווח הזה. יש לבקש למלא או לבנות מחדש את הסידור הקיים")
        plan.update(period_starts_on=period_first, period_ends_on=period_last,
                    creation_slots=build_slots(state["profile"], period_first, period_last))
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
    if turn.get("copy_from_date"):
        if first != last:
            raise _Rejected("העתקת יום דורשת תאריך יעד יחיד")
        generated = copied_day(repository, team_id, turn["copy_from_date"], first,
                               state["profile"], plan["preserved_assignments"], turn.get("required_assignments"))
        plan["copy_from_date"] = turn["copy_from_date"]
    elif partial or first == last:
        generated = scheduler.generate_span(
            state["profile"], first, last, availability=state["availability"],
            history=history.before(team_id, iso(schedule.get("starts_on")) or first),
            preferences=state["preferences"], instructions=turn.get("instructions") or "",
            required_assignments=required,
            already_scheduled=[model_assignment(row) for row in outside],
        )
    else:
        generated = scheduler.generate_verified(
            state["profile"], first, last, availability=state["availability"],
            history=history.before(team_id, first),
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
    plan["warnings"] = audit_plan(state["profile"], pseudo,
                                       context_rows + generated["assignments"], state["availability"], [])
    add_coverage(plan, state["profile"])
