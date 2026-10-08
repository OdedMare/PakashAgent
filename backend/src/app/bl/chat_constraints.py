"""Validated constraint edits and feedback from the same audit as the board."""

import datetime

from app.bl.audit import constraint_conflicts
from app.bl.audit.roster import index_shifts, rows_of
from app.bl.chat_contract import RejectedPlan, audit_plan
from app.bl.placement.values import warning_key
from app.bl.scheduler.availability import effective_availability
from app.bl.simulate.hypothetical import schedule_rows
from app.bl.tools.values import iso


def normalize_constraints(offered, profile, saved):
    if not isinstance(offered, list) or len(offered) > 126:
        raise RejectedPlan("אפשר לעדכן עד 126 אילוצים בתוכנית אחת")
    names = {row["name"] for row in profile.get("employees") or []}
    shifts = {row["name"] for row in profile.get("shifts") or []} | {""}
    by_id = {row["id"]: row for row in saved}
    result, seen = [], set()
    for row in offered:
        if not isinstance(row, dict) or row.get("action", "set") not in ("set", "remove"):
            raise RejectedPlan("פעולת האילוץ אינה תקינה")
        if row.get("action") == "remove":
            before = by_id.get(row.get("id"))
            if not before:
                raise RejectedPlan("האילוץ להסרה לא נמצא בצוות. קראו constraints_report והשתמשו במזהה שנשמר")
            item = dict(action="remove", id=before["id"], employee=before["employee"],
                        date=iso(before["constraint_date"]), shift=before.get("shift_name") or "",
                        available=bool(before.get("available")), is_hard=before.get("is_hard", True),
                        start_time=before.get("start_time") or "", end_time=before.get("end_time") or "",
                        reason=before.get("reason") or "")
        else:
            if row.get("employee") not in names or row.get("shift", "") not in shifts:
                raise RejectedPlan("האילוץ חייב להתייחס לעובד ולמשמרת מוכרים")
            try:
                date = datetime.date.fromisoformat(row.get("date") or "").isoformat()
                times = {key: datetime.time.fromisoformat(row[key]).strftime("%H:%M") if row.get(key) else ""
                         for key in ("start_time", "end_time")}
            except (ValueError, TypeError):
                raise RejectedPlan("תאריך או שעת האילוץ אינם תקינים")
            if any(key in row and not isinstance(row[key], bool) for key in ("available", "is_hard")):
                raise RejectedPlan("זמינות ועדיפות האילוץ חייבות להיות ערכים בוליאניים")
            item = dict(action="set", employee=row["employee"], date=date, shift=row.get("shift") or "",
                        available=row.get("available", False), is_hard=row.get("is_hard", True),
                        reason=row.get("reason") or "", **times)
        key = (item["employee"], item["date"], item["shift"])
        if key in seen:
            raise RejectedPlan("התוכנית מכילה יותר מעדכון אחד לאותו אילוץ")
        seen.add(key)
        result.append(item)
    return result


def edited_availability(saved, offered):
    rows = {(row["employee"], iso(row["constraint_date"]), row.get("shift_name") or ""): row for row in saved}
    for item in offered:
        key = (item["employee"], item["date"], item.get("shift") or "")
        if item.get("action") == "remove":
            rows.pop(key, None)
        else:
            rows[key] = dict(item, constraint_date=item["date"], shift_name=item.get("shift") or "", source="agent")
    return list(rows.values())


def affected_periods(repository, team_id, constraints):
    dates = {row["date"] for row in constraints}
    return [repository.get_schedule(row["id"], team_id) for row in repository.list_schedules(team_id)
            if any(iso(row["starts_on"]) <= date <= iso(row["ends_on"]) for date in dates)]


def constraint_facts(profile, periods, saved, first, last, employee=""):
    effective = effective_availability(profile, saved, first, last)
    ids = {(row["employee"], iso(row["constraint_date"]), row.get("shift_name") or ""): row.get("id", "") for row in saved}
    shifts = index_shifts(profile.get("shifts"))
    assignments = []
    for period in periods:
        assignments.extend(dict(row, schedule_id=period["id"]) for row in
                           rows_of(schedule_rows(period), shifts, period.get("slots")))
    result = []
    for item in effective:
        if employee and item["employee"] != employee:
            continue
        matches = [row for row in assignments if row["employee"] == item["employee"] and row["date"] == item["date"]
                   and (not item["shift"] or row["shift"] == item["shift"])]
        conflicts = [dict(date=row["date"], shift=row["shift"], schedule_id=row["schedule_id"])
                     for row in matches if constraint_conflicts(row, item)]
        covered = any(iso(period["starts_on"]) <= item["date"] <= iso(period["ends_on"]) for period in periods)
        unknown_hours = bool(item.get("start_time") or item.get("end_time")) and any(
            row["start"] is None or row["end"] is None for row in matches)
        status = "conflict" if conflicts else "unchecked" if not covered or unknown_hours else "honored"
        result.append(dict(item, id=ids.get((item["employee"], item["date"], item["shift"]), ""),
                           status=status, conflicts=conflicts))
    return sorted(result, key=lambda row: (not bool(row["id"]), row["date"], row["employee"], row["shift"]))


def constraints_report(repository, team_id, arguments, visible_week="", focused_id=""):
    first, last = arguments.get("starts_on") or "", arguments.get("ends_on") or ""
    period_id = arguments.get("schedule_id") or (focused_id if not first and not arguments.get("day") else "")
    if period_id and not first:
        period = repository.get_schedule(period_id, team_id)
        first, last = iso(period["starts_on"]), iso(period["ends_on"])
    elif not first:
        first = arguments.get("day") or visible_week or ""
        if not first:
            raise RejectedPlan("בחרו שבוע או ציינו טווח תאריכים לדוח האילוצים")
        last = first if arguments.get("day") else (datetime.date.fromisoformat(first) + datetime.timedelta(days=6)).isoformat()
    if not last or first > last or (datetime.date.fromisoformat(last) - datetime.date.fromisoformat(first)).days > 92:
        raise RejectedPlan("דוח אילוצים דורש טווח מלא של עד 93 ימים")
    employee = arguments.get("employee") or ""
    profile = repository.team_profile(team_id) or {}
    if employee and employee not in {row["name"] for row in profile.get("employees") or []}:
        raise RejectedPlan("העובד לא נמצא בצוות. השתמשו בשם המלא")
    periods = [repository.get_schedule(row["id"], team_id) for row in repository.list_schedules(team_id)
               if iso(row["starts_on"]) <= last and first <= iso(row["ends_on"])]
    saved = repository.availability(team_id, first, last)
    facts = constraint_facts(profile, periods, saved, first, last, employee)
    pending = [row for row in repository.list_requests(team_id, status="pending")
               if first <= iso(row["constraint_date"]) <= last and (not employee or row["employee"] == employee)]
    return dict(tool="constraints_report", ok=True, starts_on=first, ends_on=last,
                constraints=facts[:200], total=len(facts), truncated=len(facts) > 200,
                pending_requests=pending[:100], pending_total=len(pending),
                summary={status: sum(row["status"] == status for row in facts) for status in ("conflict", "honored", "unchecked")})


def constraint_impact(profile, periods, saved, offered):
    updated = edited_availability(saved, offered)
    feedback, warnings = [], []
    for date in sorted({row["date"] for row in offered}):
        facts = constraint_facts(profile, periods, updated, date, date)
        for item in (row for row in offered if row["date"] == date):
            if item.get("action") == "remove":
                feedback.append(dict(item, status="removed", conflicts=[]))
                continue
            fact = next(row for row in facts if row["employee"] == item["employee"] and row["date"] == date
                        and row["shift"] == item.get("shift", ""))
            feedback.append(fact)
    for period in periods:
        before = {warning_key(row) for row in audit_plan(profile, period, schedule_rows(period), saved, [])}
        warnings.extend(dict(row, schedule_id=period["id"]) for row in
                        audit_plan(profile, period, schedule_rows(period), updated, []) if warning_key(row) not in before)
    return feedback, warnings
