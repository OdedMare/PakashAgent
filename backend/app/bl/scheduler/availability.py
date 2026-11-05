"""Who may work when: dated constraints plus everything the profile implies."""

import copy
import datetime
import hashlib
import json
import threading
from collections import OrderedDict
from typing import Any, List

from app.bl.shared import hebrew_weekday, switched_off, weekday_key
from app.bl.scheduler.rotation_rows import (
    closure_availability, overridden, rotation_availability,
)
from app.bl.scheduler.values import (
    bounded, bounded_rows, date_text, dates_between, named, parse_date,
)

# Why a switched-off soldier is unavailable on every date of a build.
OFF_DUTY_REASON = "כבוי/ה — לא משתתף/ת בשיבוץ"


# Recent answers, by a fingerprint of everything the answer is computed
# from. One replacement search asks the same question once per shift it
# covers and again per audit of the plan; on 70 people with a rotation each
# answer took seconds, and the repeats pushed the request past the proxy.
_CACHE: "OrderedDict[str, List[dict]]" = OrderedDict()
_CACHE_SIZE = 16
_CACHE_LOCK = threading.Lock()


def effective_availability(
    profile: dict, rows: Any, starts_on: str, ends_on: str
) -> List[dict]:
    """`_effective_availability`, remembered for identical inputs.

    A pure function of its arguments, so the same profile, rows and dates
    always give the same list; each caller gets its own copy, so one that
    edits what it was handed cannot change another's answer.
    """
    try:
        key = hashlib.sha256(json.dumps(
            [profile, rows, starts_on, ends_on], sort_keys=True, default=str,
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        return _effective_availability(profile, rows, starts_on, ends_on)
    with _CACHE_LOCK:
        known = _CACHE.get(key)
        if known is not None:
            _CACHE.move_to_end(key)
            return copy.deepcopy(known)
    found = _effective_availability(profile, rows, starts_on, ends_on)
    with _CACHE_LOCK:
        _CACHE[key] = copy.deepcopy(found)
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return found


def _effective_availability(
    profile: dict, rows: Any, starts_on: str, ends_on: str
) -> List[dict]:
    """Dated constraints plus structured recurring constraints from setup.

    Explicit dated rows win for the same person, date and shift. A recurring
    all-shifts rule is expanded per declared shift, which lets one dated shift
    exception override only that occurrence. Group presence and closure cycles
    remain hard constraints even when a person submits a dated availability.
    """
    start, end = parse_date(starts_on), parse_date(ends_on)
    explicit = _explicit_rows(rows, start, end)
    if start is None or end is None or end < start:
        return explicit
    keys = {(row["employee"], row["date"], row["shift"]) for row in explicit}
    return (
        rotation_availability(profile, start, end, keys)
        + closure_availability(profile, start, end, keys)
        + _recurring_rows(profile, start, end, keys)
        + _inactive_rows(profile, start, end)
        + _disabled_reserve_rows(profile, start, end)
        + explicit
    )


def _inactive_rows(profile, start, end):
    result = []
    for person in profile.get("employees") or []:
        if switched_off(person):
            result += [dict(employee=person["name"], date=day.isoformat(), shift="",
                            available=False, is_hard=True, reason=OFF_DUTY_REASON,
                            source="off_duty") for day in dates_between(start, end)]
            continue
        first = parse_date(person.get("inactive_from") or "")
        if first is None or first > end:
            continue
        for day in dates_between(max(start, first), end):
            result.append(dict(employee=person["name"], date=day.isoformat(), shift="",
                               available=False, is_hard=True, reason="סיום עבודה", source="retirement"))
    return result


def _disabled_reserve_rows(profile, start, end):
    """Block every reservist when the unit-wide reserve switch is off."""
    if (profile.get("workplace") or {}).get("reserve_enabled") is not False:
        return []
    return [
        dict(employee=person["name"], date=day.isoformat(), shift="",
             available=False, is_hard=True, reason="המילואים כבויים", source="reserve")
        for person in profile.get("employees") or []
        if person.get("service_type") == "reserve"
        for day in dates_between(start, end)
    ]


def _explicit_rows(rows: Any, start, end) -> List[dict]:
    explicit = []
    for row in bounded_rows(rows, 2000):
        date = date_text(row.get("date") or row.get("constraint_date"))
        if not date:
            continue
        parsed = parse_date(date)
        constraint_type = bounded(row.get("constraint_type")) or "availability"
        # A duty may reach a night shift on either edge: the day before the
        # span (crossing into its first morning), or the day after it (from
        # midnight, over the last night).
        reach = datetime.timedelta(days=1 if constraint_type == "duty" else 0)
        if start is not None and end is not None and (
            parsed is None or parsed < start - reach or parsed > end + reach
        ):
            continue
        explicit.append({
            "employee": bounded(row.get("employee")),
            "date": date,
            "shift": bounded(row.get("shift") or row.get("shift_name")),
            "available": bool(row.get("available")),
            "start_time": bounded(row.get("start_time")),
            "end_time": bounded(row.get("end_time")),
            "is_hard": row.get("is_hard", True) is not False,
            "reason": bounded(row.get("reason")),
            "source": bounded(row.get("source")),
            "constraint_type": constraint_type,
        })
    return explicit


def _recurring_rows(
    profile: dict, start: datetime.date, end: datetime.date, keys: set,
) -> List[dict]:
    shift_names = [
        bounded(shift.get("name"))
        for shift in named((profile or {}).get("shifts"))
    ]
    rows = []
    for person in (profile or {}).get("employees") or []:
        if not isinstance(person, dict):
            continue
        employee = bounded(person.get("name"))
        for rule in person.get("recurring_constraints") or []:
            if employee and isinstance(rule, dict):
                rows.extend(_expand_rule(
                    employee, rule, start, end, keys, shift_names
                ))
    return rows


def _expand_rule(
    employee: str,
    rule: dict,
    start: datetime.date,
    end: datetime.date,
    keys: set,
    shift_names: List[str],
) -> List[dict]:
    """One recurring rule as a dated row per matching day and shift."""
    days = {
        weekday_key(item) for item in rule.get("days") or []
        if weekday_key(item)
    }
    offered = [value for value in (bounded(item) for item in rule.get("shifts") or []) if value]
    shifts = offered or shift_names or [""]
    rows = []
    for day in dates_between(start, end):
        if days and weekday_key(hebrew_weekday(day)) not in days:
            continue
        date = day.isoformat()
        for shift in shifts:
            if overridden(keys, employee, date, shift):
                continue
            rows.append({
                "employee": employee,
                "date": date,
                "shift": shift,
                "available": bool(rule.get("available")),
                "start_time": bounded(rule.get("start_time")),
                "end_time": bounded(rule.get("end_time")),
                "is_hard": rule.get("is_hard", True) is not False,
                "reason": bounded(rule.get("reason")),
                "source": bounded(rule.get("source")) or "setup",
                "constraint_type": bounded(rule.get("constraint_type")) or "availability",
            })
    return rows


def availability_for_dates(rows: Any, dates: set) -> List[dict]:
    return [
        row for row in bounded_rows(rows, 2000)
        if date_text(row.get("date") or row.get("constraint_date")) in dates
    ]
