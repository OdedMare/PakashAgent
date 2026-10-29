"""Read-only preparation of departures and shift-grid migrations."""

import datetime
import json

from app.bl.chat_contract import NeedsManager, RejectedPlan
from app.bl.chat_schema import PROFILE_SECTIONS
from app.bl.scheduler import build_slots
from app.bl.simulate.hypothetical import schedule_rows
from app.bl.tools.values import iso
from app.common.errors import AppError


def date_value(value, question):
    try:
        return datetime.date.fromisoformat(value or "").isoformat()
    except (ValueError, TypeError):
        raise NeedsManager(question)


def future_schedules(repository, team_id, first):
    return [repository.get_schedule(row["id"], team_id)
            for row in repository.list_schedules(team_id) if iso(row["ends_on"]) >= first]


def prepare_blank(turn, plan, state, profile):
    try:
        first = datetime.date.fromisoformat(turn.get("starts_on") or "")
        last = datetime.date.fromisoformat(turn.get("ends_on") or "")
    except (ValueError, TypeError):
        raise RejectedPlan("יש לציין תאריכים מוחלטים לסידור הריק")
    if first > last or (last - first).days > 30:
        raise RejectedPlan("סידור ריק דורש טווח של עד 31 ימים")
    if any(
        iso(row["starts_on"]) <= last.isoformat()
        and first.isoformat() <= iso(row["ends_on"])
        for row in state["periods"]
    ):
        raise RejectedPlan(
            "כבר קיים סידור בטווח הזה. אין ליצור סידור חופף; "
            "אפשר לרוקן או לערוך את הקיים"
        )
    slots = build_slots(profile, first.isoformat(), last.isoformat())
    if not slots:
        raise RejectedPlan("אין משמרות מוגדרות לתאריכים האלה. יש להשלים את הגדרות המשמרות")
    plan.update(
        starts_on=first.isoformat(), ends_on=last.isoformat(), creation_slots=slots,
    )
    return plan


def prepare_profile(profiles, team_id, turn, plan, profile):
    try:
        patch = json.loads(turn.get("profile_patch_json") or "{}")
    except ValueError as exc:
        raise RejectedPlan("עריכת הפרופיל אינה תקינה. אפשר לנסח שוב") from exc
    if not isinstance(patch, dict) or not patch or set(patch) - set(PROFILE_SECTIONS):
        raise RejectedPlan("לא זוהה שינוי תקין בפרטי הצוות")
    for section in ("employees", "shifts"):
        if section not in patch:
            continue
        if not isinstance(patch[section], list) or any(
            not isinstance(row, dict) for row in patch[section]
        ):
            raise RejectedPlan("פרטי העובדים והמשמרות חייבים להיות רשימת רשומות")
        existing = {row["name"]: row for row in profile.get(section) or []}
        if section == "employees":
            _validate_new_employees(patch[section], existing)
        changed = {row.get("name"): dict(existing.get(row.get("name"), {}), **row)
                   for row in patch[section]}
        # A patch names the rows it adds or changes; every other row stays as
        # it is. Asking the model to resend a hundred-person roster to add one
        # recurring constraint is slow and is how somebody else's field is lost.
        patch[section] = [changed.pop(name, row) for name, row in existing.items()] \
            + list(changed.values())
    try:
        updated = profiles.preview(team_id, **patch)
    except AppError as exc:
        raise RejectedPlan(str(exc)) from exc
    plan["profile_patch"] = patch
    plan["profile_before"] = {key: profile.get(key) for key in patch}
    plan["profile_after"] = {key: updated.get(key) for key in patch}


def _validate_new_employees(rows, existing):
    required = {
        "role", "eligible_shifts", "service_type", "exit_pattern", "rotation_group",
    }
    for row in rows:
        missing = required - set(row)
        if row.get("name") not in existing and missing:
            raise RejectedPlan(
                "לעובד החדש חסרים שדות: %s. יש לשמור את הפרטים שהמנהל נתן ולא לנחש"
                % ", ".join(sorted(missing))
            )


def prepare_retirement(repository, profiles, team_id, turn, plan, state):
    name = (turn.get("employee") or "").strip()
    people = state["profile"].get("employees") or []
    if name not in {row["name"] for row in people}:
        raise NeedsManager("איזה עובד מסיים את העבודה?")
    first = date_value(turn.get("effective_date"), "מאיזה תאריך העובד מסיים את העבודה?")
    person = next(row for row in people if row["name"] == name)
    if person.get("inactive_from"):
        raise RejectedPlan("העובד כבר הוצא מהסגל הפעיל. אין צורך להסיר אותו שוב")
    updated = profiles.preview(team_id, employees=[
        dict(row, inactive_from=first) if row["name"] == name else dict(row) for row in people])
    periods = future_schedules(repository, team_id, first)
    affected = []
    for period in periods:
        removed = [row for row in period["assignments"]
                   if row["employee"] == name and iso(row["date"]) >= first]
        if not removed:
            continue
        affected.append(dict(schedule_id=period["id"], operations=[
            dict(action="remove", employee=name, shift=row["shift"], date=iso(row["date"]),
                 reason=plan["reason"]) for row in removed]))
    plan.update(employee=name, effective_date=first, updated_profile=updated,
                profile_before={"employees": people}, profile_after={"employees": updated["employees"]},
                affected_schedules=affected, operations=[row for period in affected for row in period["operations"]],
                starts_on=first, ends_on=max([iso(row["ends_on"]) for row in periods] or [first]))
    return periods


def prepare_structure(profiles, scheduler, team_id, turn, plan, state, history, audit_plan):
    schedule = state["schedule"]
    if not schedule:
        raise RejectedPlan("בחרו טיוטת סידור לשינוי מבנה המשמרות")
    try:
        patch = json.loads(turn.get("profile_patch_json") or "{}")
    except ValueError:
        raise RejectedPlan("הגדרות המשמרות אינן תקינות")
    if not isinstance(patch, dict) or set(patch) - {"shifts", "employees"} or not patch.get("shifts"):
        raise RejectedPlan("שינוי המבנה דורש רשימת משמרות מלאה, ופרטי עובדים רק לצורך מיפוי הכשירות והאילוצים")
    for row in patch["shifts"]:
        if not isinstance(row, dict) or not row.get("start_time") or not row.get("end_time"):
            raise NeedsManager("מה שעות ההתחלה והסיום של כל משמרת חדשה?")
        if not row.get("staffing") and not row.get("headcount"):
            raise NeedsManager("כמה עובדים ואילו תפקידים נדרשים בכל משמרת חדשה?")
    updated = profiles.preview_structure(team_id, patch["shifts"], patch.get("employees"))
    names = {row["name"] for row in updated["shifts"]}
    unresolved = []
    for person in updated["employees"]:
        old = set(person.get("eligible_shifts") or []) - names
        scopes = [rule for rule in person.get("recurring_constraints") or []
                  if isinstance(rule, dict) and set(rule.get("shifts") or []) - names]
        if old or scopes:
            unresolved.append(person["name"])
    if unresolved:
        raise NeedsManager("לאילו משמרות חדשות מתאימים העובדים %s, ואיך למפות את האילוצים שלהם?" % ", ".join(unresolved))
    first = date_value(turn.get("starts_on") or iso(schedule["starts_on"]), "מאיזה תאריך לשנות את המשמרות?")
    last = date_value(turn.get("ends_on") or iso(schedule["ends_on"]), "עד איזה תאריך לעדכן את הטיוטה?")
    if not (iso(schedule["starts_on"]) <= first <= last <= iso(schedule["ends_on"])):
        raise RejectedPlan("טווח שינוי המשמרות חייב להיות בתוך הטיוטה שנבחרה")
    outside = [row for row in schedule_rows(schedule) if not first <= row["date"] <= last]
    existing = [row for row in schedule_rows(schedule) if first <= row["date"] <= last]
    # The solver keeps each existing row where it still fits (`keep`), so a
    # changed vocabulary moves as few people as it can.
    generated = scheduler.generate_verified(updated, first, last, availability=state["availability"],
        history=history, preferences=state["preferences"], instructions=turn.get("instructions") or "",
        required_assignments=turn.get("required_assignments") or [], already_scheduled=outside,
        keep=existing)
    new_slots = [dict(row) for row in schedule["slots"] if not first <= iso(row["slot_date"]) <= last]
    new_slots += generated["slots"]
    imagined = dict(schedule, slots=new_slots)
    plan.update(updated_profile=updated, profile_before={key: state["profile"].get(key) for key in patch},
                profile_after={key: updated.get(key) for key in patch}, starts_on=first, ends_on=last,
                generated=generated, replacement_slots=new_slots,
                warnings=audit_plan(updated, imagined, outside + generated["assignments"], state["availability"], []))


def copied_day(repository, team_id, source, target, profile, preserved, overrides):
    source = date_value(source, "מאיזה תאריך להעתיק את השיבוץ?")
    periods = [row for row in repository.list_schedules(team_id)
               if iso(row["starts_on"]) <= source <= iso(row["ends_on"])]
    if len(periods) != 1:
        raise NeedsManager("לא נמצא סידור יחיד לתאריך המקור. מאיזה יום להעתיק?")
    original = repository.get_schedule(periods[0]["id"], team_id)
    rows = [dict(employee=row["employee"], shift=row["shift"], date=target,
                 reason="העתקת השיבוץ מתאריך " + source)
            for row in original["assignments"] if iso(row["date"]) == source]
    if not rows:
        raise NeedsManager("ביום המקור אין שיבוצים. מאיזה יום אחר להעתיק?")
    slots = build_slots(profile, target, target)
    names = {row["shift_name"] for row in slots}
    if any(row["shift"] not in names for row in rows):
        raise NeedsManager("סוגי המשמרות ביום המקור שונים. איך למפות אותם למשמרות הנוכחיות?")
    if overrides:
        rows = [dict(row, reason="תיקון ההעתקה לפי בחירת המנהל") for row in overrides]
    # Filling keeps already saved placements; a saved slot replaces its copied
    # counterpart, rather than accidentally creating two people in one seat.
    pinned_slots = {(row["date"], row["shift"]) for row in preserved}
    rows = preserved + [row for row in rows if (row["date"], row["shift"]) not in pinned_slots]
    return dict(slots=slots, assignments=rows, notes=[], summary="העתקת שיבוץ ליום שנבחר")
