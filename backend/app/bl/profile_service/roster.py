"""Validating the roster: service types, exit patterns, rotation groups."""

import datetime
import re
from typing import Any, List

from app.bl.profile_service import unit as unit_rules
from app.bl.profile_service.validation import named_rows, text, text_list, valid_time
from app.bl.rotation.vocabulary import groups_for
from app.bl.shared import HEBREW_WEEKDAYS, weekday_key
from app.common.errors import AgentError

# civilian = אע״צ (אזרח עובד צה״ל), hatzach = הצ״ח. Both sit beside reserve
# (מילואים) as a status of the person; neither takes reserve days, and
# neither changes how the solver places them — only how they are labelled
# and coloured on the board.
_SERVICE_TYPES = ("standard", "overlap", "reserve", "civilian", "hatzach")
_RANK_GROUPS = ("officer", "nco")
_EXIT_PATTERNS = ("round", "triplet", "quad", "quint", "hamshushim", "shushim",
                  "none", "daily", "personal")
# Patterns one person carries alone (`rotation/personal.py`): no group.
_PERSONAL = ("none", "daily", "personal")
_GROUPED = ("round", "triplet", "quad", "quint")
# How capable a soldier is, weakest first. Optional: an empty value is "not
# rated", and the solver balances only the people who are (`solver/competence.py`).
COMPETENCE_LEVELS = ("weak", "medium", "high", "excellent")
# How a reservist was called up: an emergency order (צו 8) or reserve days.
_RESERVE_CALLS = ("order", "days")
# A day cycle is named by its id; whether that id exists is checked against
# the workplace in `validate_rotation_groups`, once both halves are merged.
_DAY_CYCLE = re.compile(r"^cycle:[A-Za-z0-9_-]{1,32}$")


def employees(rows: Any, default_exit_pattern: str = "round") -> List[dict]:
    return [_employee(row, default_exit_pattern) for row in named_rows(rows, "עובד")]


def _employee(row: dict, default_exit_pattern: str) -> dict:
    raw = dict(row)
    if row.get("inactive_from"):
        try:
            row["inactive_from"] = datetime.date.fromisoformat(row["inactive_from"]).isoformat()
        except (ValueError, TypeError):
            raise AgentError("תאריך סיום העבודה חייב להיות בפורמט YYYY-MM-DD")
    service_type = text(row.get("service_type")) or "standard"
    if service_type not in _SERVICE_TYPES:
        raise AgentError("סוג כוח האדם אינו תקין")
    rank_group = text(row.get("rank_group"))
    if rank_group and rank_group not in _RANK_GROUPS:
        raise AgentError("דרג התקן אינו תקין")
    exit_pattern = text(row.get("exit_pattern")) or default_exit_pattern
    if exit_pattern not in _EXIT_PATTERNS and not _DAY_CYCLE.match(exit_pattern):
        raise AgentError("מבנה היציאות של איש הצוות אינו תקין")
    recurring = row.get("recurring_constraints") or []
    if not isinstance(recurring, list):
        raise AgentError("האילוצים הקבועים של איש הצוות אינם תקינים")
    _validate_recurring(recurring)
    row.update(_soldier_fields(row, service_type))
    row.update(_personal_fields(row, exit_pattern))
    row.update({
        "service_type": service_type,
        "rank_group": rank_group,
        "exit_pattern": exit_pattern,
        # Kept for every pattern, because a group is what makes one rotate:
        # a חמשושים person *with* a group goes out on their group's weekends.
        "rotation_group": "" if exit_pattern in _PERSONAL else text(row.get("rotation_group")),
        "role": text(row.get("role")),
        "notes": text(row.get("notes")),
        "is_shift_manager": bool(row.get("is_shift_manager")),
        "can_train": bool(row.get("can_train")),
        "eligible_shifts": text_list(row.get("eligible_shifts") or []),
        "is_trainee": service_type == "overlap",
        "is_casual": service_type == "reserve",
        "recurring_constraints": recurring,
    })
    row.pop("qualifications", None)
    row.update(unit_rules.person_fields(dict(raw)))
    if not isinstance(row.get("counts_toward_staffing"), bool):
        row["counts_toward_staffing"] = service_type != "overlap"
    return row


def _soldier_fields(row: dict, service_type: str) -> dict:
    """Competence for anyone; days a week and call-up type for a reservist.

    A reservist's fields are dropped once they stop being one, so a soldier
    moved back to standard service is not capped by a week they no longer owe.
    """
    competence = text(row.get("competence"))
    if competence and competence not in COMPETENCE_LEVELS:
        raise AgentError("הרמה המקצועית אינה תקינה (חלש, בינוני, גבוה או מצטיין)")
    fields = {"competence": competence, "reserve_days_per_week": None,
              "reserve_min_days": None, "reserve_consecutive": False, "reserve_call": ""}
    if service_type != "reserve":
        return fields
    days = _week_days(row.get("reserve_days_per_week"), "מספר ימי המילואים בשבוע")
    least = _week_days(row.get("reserve_min_days"), "מינימום ימי המילואים בשבוע")
    if least is not None and days is not None and least > days:
        raise AgentError("מינימום ימי המילואים בשבוע גדול ממספר הימים שהחייל/ת מגיע/ה")
    fields["reserve_days_per_week"] = days
    fields["reserve_min_days"] = least
    consecutive = row.get("reserve_consecutive")
    if consecutive not in (None, "") and not isinstance(consecutive, bool):
        raise AgentError("reserve_consecutive חייב להיות ערך בוליאני")
    fields["reserve_consecutive"] = bool(consecutive)
    call = text(row.get("reserve_call"))
    if call and call not in _RESERVE_CALLS:
        raise AgentError("סוג הזימון למילואים אינו תקין (צו או ימי מילואים)")
    fields["reserve_call"] = call
    return fields


def _personal_fields(row: dict, pattern: str) -> dict:
    """Daily hours, or one weekend in N; dropped when the pattern changes."""
    fields = {"daily_days": [], "daily_start": "", "daily_end": "",
              "closure_every": None, "closure_from": ""}
    if pattern == "daily":
        days = text_list(row.get("daily_days") or [])
        weekdays = {weekday_key(day) for day in HEBREW_WEEKDAYS}
        if any(weekday_key(day) not in weekdays for day in days):
            raise AgentError("ימי ההגעה היומית חייבים להיות שמות ימים בעברית")
        for key in ("daily_start", "daily_end"):
            if text(row.get(key)) and not valid_time(text(row.get(key))):
                raise AgentError("שעות ההגעה היומית חייבות להיות בפורמט HH:MM")
            fields[key] = text(row.get(key))
        fields["daily_days"] = days
    elif pattern == "personal":
        count = row.get("closure_every")
        try:
            count = int(count) if count not in (None, "") and not isinstance(count, bool) else None
        except (TypeError, ValueError):
            count = -1
        if count is not None and not 2 <= count <= 8:
            raise AgentError("סגירה אישית היא שבת אחת מכל 2 עד 8 שבתות")
        first = text(row.get("closure_from"))
        if first:
            try:
                first = datetime.date.fromisoformat(first).isoformat()
            except ValueError:
                raise AgentError("תאריך הסגירה הראשונה חייב להיות בפורמט YYYY-MM-DD")
        fields.update(closure_every=count, closure_from=first)
    return fields


def _week_days(value, what: str):
    """A count of days in one week, 1–7, or None when not stated."""
    if value in (None, ""):
        return None
    error = "%s חייב להיות בין 1 ל-7" % what
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise AgentError(error)
    try:
        days = int(float(value))
    except ValueError:
        raise AgentError(error)
    if not 1 <= days <= 7:
        raise AgentError(error)
    return days


def _validate_recurring(rows: list) -> None:
    weekdays = {weekday_key(day) for day in HEBREW_WEEKDAYS}
    fields = {"days", "shifts", "available", "is_hard", "start_time", "end_time", "reason", "source", "constraint_type"}
    for rule in rows:
        if isinstance(rule, str):
            # Older free-text profile prose is preserved; only structured rules expand.
            continue
        if not isinstance(rule, dict) or set(rule) - fields \
                or not isinstance(rule.get("days"), list) \
                or not isinstance(rule.get("shifts"), list) \
                or not isinstance(rule.get("available"), bool):
            raise AgentError("אילוץ קבוע חייב להכיל days ו-shifts כרשימות ו-available כערך בוליאני; אין להשתמש ב-day_of_week או shift")
        if any(weekday_key(day) not in weekdays for day in rule["days"]) \
                or any(not isinstance(shift, str) or not shift.strip() for shift in rule["shifts"]):
            raise AgentError("ימי האילוץ חייבים להיות שמות ימים בעברית, והמשמרות חייבות להיות רשימת שמות")
        if "is_hard" in rule and not isinstance(rule["is_hard"], bool):
            raise AgentError("is_hard באילוץ קבוע חייב להיות ערך בוליאני")
        if any(rule.get(key) and (not isinstance(rule[key], str) or not valid_time(rule[key]))
               for key in ("start_time", "end_time")):
            raise AgentError("שעות האילוץ הקבוע חייבות להיות בפורמט HH:MM")
        constraint_type = rule.get("constraint_type") or "availability"
        if constraint_type not in ("availability", "duty"):
            raise AgentError("סוג האילוץ הקבוע אינו תקין")
        if constraint_type == "duty" and (
            rule["available"] or rule.get("is_hard", True) is False
            or rule["shifts"] or not rule.get("start_time") or not rule.get("end_time")
        ):
            raise AgentError("תורנות קבועה חייבת להיות קשיחה, עם שעת התחלה וסיום וללא משמרת מסוימת")


def employee_item(item: dict) -> dict:
    """An agent-proposed roster row, in the shape the editor writes."""
    return {
        "name": item.get("name"),
        "role": item.get("role") or "",
        "eligible_shifts": item.get("eligible_shifts") or [],
        "exit_pattern": item.get("exit_pattern") or "round",
        "rotation_group": item.get("rotation_group") or "",
        "is_shift_manager": bool(item.get("is_shift_manager")),
        "can_train": bool(item.get("can_train")),
        "notes": item.get("notes") or "",
        "competence": item.get("competence") or "",
        **({"rank_group": item.get("rank_group") or ""} if "rank_group" in item else {}),
        **{key: item[key] for key in ("service_type", "reserve_days_per_week", "reserve_min_days",
                                 "reserve_consecutive", "reserve_call", "daily_days",
                                 "daily_start", "daily_end", "closure_every", "closure_from")
           if item.get(key) not in (None, "")},
    }


def validate_rotation_groups(profile: dict) -> None:
    """Every stated group belongs to the cycle its owner turns on.

    חמשושים and שושים say how long a closure runs, not how many groups take
    turns, so their group is checked against the unit's own cycle.
    """
    workplace = profile.get("workplace") or {}
    mode = text(workplace.get("rotation_mode")) or "round"
    cycles = {
        "cycle:%s" % text(row.get("id")): row for row in workplace.get("day_cycles") or []
        if isinstance(row, dict)
    }
    for person in profile.get("employees") or []:
        pattern = text(person.get("exit_pattern")) or mode
        if pattern.startswith("cycle:"):
            _check_day_cycle(person, cycles.get(pattern))
            continue
        if pattern in _PERSONAL:
            continue
        cycle = pattern if pattern in _GROUPED else mode
        groups = set(groups_for(cycle) or groups_for("round"))
        group = text(person.get("rotation_group"))
        if group and group not in groups:
            raise AgentError("קבוצת הסבב של %s אינה מתאימה למבנה היחידה" % (
                text(person.get("name")) or "איש הצוות"
            ))


def _check_day_cycle(person: dict, cycle) -> None:
    name = text(person.get("name")) or "איש הצוות"
    if cycle is None:
        raise AgentError("מחזור היציאות של %s אינו מוגדר ביחידה" % name)
    if text(person.get("rotation_group")) not in (cycle.get("groups") or []):
        raise AgentError("יש לבחור ל%s קבוצה מתוך %s" % (name, text(cycle.get("name")) or "המחזור"))


def validate_first_profile(profile: dict) -> None:
    if not text((profile.get("workplace") or {}).get("name")):
        raise AgentError("יש להזין שם יחידה")
    if not profile.get("employees"):
        raise AgentError("יש להוסיף לפחות איש צוות אחד")
    workplace = profile.get("workplace") or {}
    if any(
        person.get("exit_pattern") in _GROUPED and not text(person.get("rotation_group"))
        and _anchored(workplace, person["exit_pattern"])
        for person in profile.get("employees") or []
    ):
        raise AgentError("יש לבחור קבוצת סבב, תלתון, רבעון או חמישון לכל איש צוות מתאים")
    if not profile.get("shifts"):
        raise AgentError("יש להוסיף לפחות סוג משמרת אחד")


def _anchored(workplace: dict, pattern: str) -> bool:
    """Whether the unit runs this weekend cycle at all. A unit with no
    closure anchor (a reserve unit on 12-hour shifts, no weekend rotation)
    leaves its people ungrouped, which means no rotation."""
    if pattern == "round" and text(workplace.get("first_closure_date")):
        return True
    return bool(text(workplace.get("%s_first_closure_date" % pattern)))
