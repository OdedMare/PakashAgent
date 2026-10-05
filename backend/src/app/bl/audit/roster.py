"""Assignments normalised into rows carrying their shift's hours.

`shift_hours` is the one weighted hours calculation in the product. Every
reader of hours -- the warnings, the personal summary, the charts -- goes
through `rows_of`, so one person's hours are literally the same arithmetic as
the manager's warnings rather than a second implementation.
"""

import datetime
from typing import Any, Dict, List, Optional

from app.bl.audit.values import (
    MINUTES_PER_HOUR, number, parse_date, parse_time, text,
)

# Defaults used only when the workplace profile does not say otherwise. They
# exist so a schedule can be audited before the profile is complete, not to
# encode a policy about what a working week looks like.
_DEFAULT_MAX_WEEKLY_HOURS = 45.0
_DEFAULT_MAX_CONSECUTIVE_DAYS = 6
_DEFAULT_MIN_REST_HOURS = 8.0


def index_shifts(shifts: Optional[List[dict]]) -> Dict[str, dict]:
    """Shift definitions by name, from the workplace's own vocabulary (D9)."""
    index: Dict[str, dict] = {}
    for shift in shifts or []:
        if isinstance(shift, dict) and text(shift.get("name")):
            index[text(shift.get("name"))] = shift
    return index


def index_people(employees: Optional[List[dict]]) -> Dict[str, dict]:
    return {
        text(person.get("name")): person
        for person in employees or []
        if isinstance(person, dict) and text(person.get("name"))
    }


def shift_hours(shift: dict) -> float:
    """Clock length times the shift's hour weight.

    On-call is the reason the weight exists: `כונן לילה` in one of the real
    files is a night a person is *available* rather than working, and the
    interview asks how it counts toward hours precisely so this does not have
    to assume (D9). A weight of 0.5 makes an eight-hour on-call count as four.
    """
    start = parse_time(shift.get("start_time"))
    end = parse_time(shift.get("end_time"))
    if start is None or end is None:
        return 0.0
    minutes = (end - start).total_seconds() / 60.0
    if end <= start:
        minutes += 24 * MINUTES_PER_HOUR
    weight = number(shift.get("hour_weight"), 1.0)
    return round((minutes / MINUTES_PER_HOUR) * weight, 2)


def row(item: Any, shift_index: Dict[str, dict]) -> Optional[dict]:
    """One assignment, normalized, with its shift's hours resolved.

    An assignment naming a shift the vocabulary does not have is kept rather
    than dropped: it still double-books and still fills a slot. It simply
    contributes no hours -- inventing a length would put a fabricated number
    in the hours total.
    """
    if not isinstance(item, dict):
        return None
    employee, date = text(item.get("employee")), text(item.get("date"))
    if not employee or not date:
        return None
    shift_name = text(item.get("shift"))
    shift = shift_index.get(shift_name) or {}
    return {
        "employee": employee,
        "shift": shift_name,
        "date": date,
        "day": parse_date(date),
        "start": parse_time(shift.get("start_time")),
        "end": parse_time(shift.get("end_time")),
        "hours": shift_hours(shift),
        "is_on_call": bool(shift.get("is_on_call")),
    }


def rows_of(assignments: Optional[List[dict]], shift_index: Dict[str, dict]) -> List[dict]:
    rows = [row(item, shift_index) for item in assignments or []]
    return [item for item in rows if item is not None]


def iso_week(day: datetime.date) -> tuple:
    year, week, _ = day.isocalendar()
    return year, week


def starts_at(item: dict) -> datetime.datetime:
    return datetime.datetime.combine(item["day"], item["start"].time())


def ends_at(item: dict) -> datetime.datetime:
    """The end instant, rolled to the next day when the shift crosses midnight."""
    end = datetime.datetime.combine(item["day"], item["end"].time())
    if item["end"] <= item["start"]:
        end += datetime.timedelta(days=1)
    return end


def policy(profile: Optional[dict]) -> dict:
    """Thresholds, taken from the profile where it states them.

    The interview collects rest and weekend policy as the manager's own
    sentences (D2), which is not a number this can read. So the thresholds
    come from an explicit `audit_policy` block when one exists and fall back
    to the defaults otherwise -- deliberately NOT parsed out of the Hebrew.
    """
    stated = (profile or {}).get("audit_policy")
    stated = stated if isinstance(stated, dict) else {}
    return {
        "max_weekly_hours": number(
            stated.get("max_weekly_hours"), _DEFAULT_MAX_WEEKLY_HOURS
        ),
        "max_consecutive_days": int(number(
            stated.get("max_consecutive_days"), _DEFAULT_MAX_CONSECUTIVE_DAYS
        )),
        "min_rest_hours": number(
            stated.get("min_rest_hours"), _DEFAULT_MIN_REST_HOURS
        ),
    }
