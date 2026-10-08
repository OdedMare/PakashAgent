"""Manager inbox and preference actions, prepared read-only before approval."""

from app.bl.chat_constraints import affected_periods, normalize_constraints, constraint_impact
from app.bl.chat_contract import NeedsManager, RejectedPlan, audit_plan
from app.bl.employee_service.requests import ConstraintRequests
from app.bl.employee_service.swaps import SwapRequests, _swap_operation
from app.bl.placement.values import warning_key
from app.bl.simulate.hypothetical import Hypothetical, schedule_rows
from app.bl.tools.values import iso
from app.common.errors.errors import AppError
from app.dal.repository.schedule_vocabulary import PREFERENCE_KINDS


ACTIONS = {
    "constraint_request": {"approve", "reject"},
    "swap_request": {"approve", "reject"},
    "preference": {"add", "update", "approve", "archive", "delete"},
}


def management_state(repository, team_id, operations):
    records, periods = [], {}
    for item in operations:
        resource, action = item.get("resource"), item.get("action")
        if resource not in ACTIONS or action not in ACTIONS[resource]:
            raise RejectedPlan("פעולת הניהול אינה נתמכת")
        before = None
        if not (resource == "preference" and action == "add"):
            if not item.get("id"):
                raise RejectedPlan("קראו את תיבת הבקשות או ההעדפות לפני פעולה; חסר מזהה רשומה")
            readers = {"constraint_request": repository.get_request,
                       "swap_request": repository.get_swap,
                       "preference": repository.get_preference}
            before = readers[resource](item["id"], team_id)
            records.append(dict(resource=resource, record=before))
        if resource == "swap_request" and action == "approve":
            period = repository.get_schedule(before["schedule_id"], team_id)
            periods[period["id"]] = period
        if resource == "constraint_request" and action == "approve":
            for period in affected_periods(repository, team_id, [{"date": iso(before["constraint_date"])}]):
                periods[period["id"]] = period
    return dict(records=records, periods=list(periods.values()))


def prepare_management(repository, team_id, turn, plan, state, request):
    offered = turn.get("management_operations") or []
    if not isinstance(offered, list) or not offered or len(offered) > 20 or any(not isinstance(row, dict) for row in offered):
        raise RejectedPlan("תוכנית ניהול דורשת בין פעולה אחת ל-20 פעולות")
    try:
        snapshot = management_state(repository, team_id, offered)
    except AppError as exc:
        raise RejectedPlan(str(exc))
    operations, seen, constraints, swaps = [], set(), [], {}
    for item in offered:
        resource, action, record_id = item["resource"], item["action"], item.get("id") or ""
        if (resource, record_id) in seen and action != "add":
            raise RejectedPlan("אותה רשומה מופיעה פעמיים בתוכנית")
        seen.add((resource, record_id))
        before = next((row["record"] for row in snapshot["records"]
                       if row["resource"] == resource and row["record"]["id"] == record_id), {})
        reason = (item.get("reason") or turn.get("stated_reason") or "").strip()
        canonical = dict(resource=resource, action=action, id=record_id, reason=reason,
                         text="", kind="", subject="", before=before)
        if resource == "preference":
            if action in ("add", "update"):
                text = (item.get("text") or "").strip()
                if not text or len(text) > 500:
                    raise RejectedPlan("העדפה צריכה להכיל בין תו אחד ל-500 תווים")
                canonical["text"] = text
            if action == "add":
                kind = item.get("kind") or "general"
                if kind not in PREFERENCE_KINDS:
                    raise RejectedPlan("סוג ההעדפה אינו תקין")
                subject = item.get("subject") or ""
                if len(subject) > 200:
                    raise RejectedPlan("נושא ההעדפה ארוך מדי")
                canonical.update(kind=kind, subject=subject)
        else:
            if before.get("status") != "pending":
                raise RejectedPlan("הבקשה כבר טופלה או עדיין ממתינה להסכמת העובד. יש לקרוא את התיבה מחדש")
            if action == "reject" and not reason:
                raise NeedsManager("איזו סיבה למסור לעובד לדחיית הבקשה?")
            canonical["reason"] = reason or request
            if resource == "constraint_request" and action == "approve":
                constraints.append(dict(employee=before["employee"], date=iso(before["constraint_date"]),
                                        shift=before.get("shift_name") or "", available=bool(before.get("available")),
                                        reason=before.get("reason") or ""))
            if resource == "swap_request" and action == "approve":
                swaps.setdefault(before["schedule_id"], []).append(_swap_operation(before))
        if len(canonical["reason"]) > 2000:
            raise RejectedPlan("סיבת הפעולה ארוכה מדי")
        operations.append(canonical)
    plan["management_operations"] = operations
    plan["constraints"] = normalize_constraints(constraints, state["profile"], state["availability"])
    periods = []
    for period in snapshot["periods"]:
        proposed = swaps.get(period["id"], [])
        after = Hypothetical(schedule_rows(period), period).apply_all(proposed)
        if after.skipped:
            raise RejectedPlan(after.skipped[0]["why"])
        # Two swaps sharing an occurrence must not silently undo each other.
        occurrences = [(row[key], row[date], row[shift]) for row in proposed
                       for key, date, shift in (("employee", "date", "shift"), ("with_employee", "with_date", "with_shift"))]
        if len(occurrences) != len(set(occurrences)):
            raise RejectedPlan("החלפות בתוכנית נוגעות באותו שיבוץ. יש לפצל אותן לתוכניות נפרדות")
        before_warnings = {warning_key(row) for row in audit_plan(state["profile"], period, schedule_rows(period), state["availability"], [])}
        warnings = audit_plan(state["profile"], period, after.rows, state["availability"], plan["constraints"])
        plan["warnings"].extend(dict(row, schedule_id=period["id"]) for row in warnings if warning_key(row) not in before_warnings)
        periods.append(dict(period, assignments=after.rows))
    plan["constraint_feedback"], _ = constraint_impact(state["profile"], periods, state["availability"], plan["constraints"])
    plan["draft_schedule_ids"] = [row["id"] for row in snapshot["periods"] if row["id"] in swaps and row["status"] == "published"]
    return snapshot


def apply_management(repository, schedules, team_id, operations):
    requests, swaps = ConstraintRequests(repository, schedules), SwapRequests(repository, schedules)
    for item in operations:
        resource, action = item["resource"], item["action"]
        if resource == "constraint_request":
            if action == "approve":
                requests.approve(team_id, item["id"], item["reason"])
            else:
                requests.reject(team_id, item["id"], item["reason"])
        elif resource == "swap_request":
            if action == "approve":
                swaps.approve_swap(team_id, item["id"], item["reason"])
            else:
                swaps.reject_swap(team_id, item["id"], item["reason"])
        elif action == "add":
            schedules.add_preference(team_id, item["text"], kind=item["kind"], subject=item["subject"], source="agent")
        elif action == "delete":
            schedules.delete_preference(team_id, item["id"])
        else:
            schedules.update_preference(team_id, item["id"],
                                        text=item["text"] if action == "update" else None,
                                        status={"approve": "active", "archive": "archived"}.get(action))
