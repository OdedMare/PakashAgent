"""Who may work when: dated constraints plus everything the profile implies."""

import datetime
from typing import Any, List

from app.bl.shared.hebrew_calendar import hebrew_weekday, weekday_key
from app.bl.scheduler.rotation_rows import (
    closure_availability, overridden, rotation_availability,
)
from app.bl.scheduler.values import (
    bounded, bounded_rows, date_text, dates_between, named, parse_date,
)


def effective_availability(
    profile: dict, rows: Any, starts_on: str, ends_on: str
) -> List[dict]:
    """Dated constraints plus structured recurring constraints from interview.

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
        + explicit
    )


def _inactive_rows(profile, start, end):
    result = []
    for person in profile.get("employees") or []:
        first = parse_date(person.get("inactive_from") or "")
        if first is None or first > end:
            continue
        for day in dates_between(max(start, first), end):
            result.append(dict(employee=person["name"], date=day.isoformat(), shift="",
                               available=False, is_hard=True, reason="סיום עבודה", source="retirement"))
    return result


def _explicit_rows(rows: Any, start, end) -> List[dict]:
    explicit = []
    for row in bounded_rows(rows, 2000):
        date = date_text(row.get("date") or row.get("constraint_date"))
        if not date:
            continue
        parsed = parse_date(date)
        if start is not None and end is not None and (
            parsed is None or parsed < start or parsed > end
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
                "source": bounded(rule.get("source")) or "interview",
            })
    return rows


def availability_for_dates(rows: Any, dates: set) -> List[dict]:
    return [
        row for row in bounded_rows(rows, 2000)
        if date_text(row.get("date") or row.get("constraint_date")) in dates
    ]
