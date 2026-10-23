"""The slot grid, and the spans a period is solved in.

Built in code: which dates fall in a period and which weekday each one is
is arithmetic. The solver assigns people into this grid.
"""

from typing import List

from app.bl.shared import hebrew_weekday, runs_on
from app.bl.scheduler.values import (
    bounded, dates_between, named, parse_date, role_list,
)
from app.common.errors import AgentError

# One leap year is a useful product ceiling; beyond that belongs in a
# separate forecast rather than one living operational schedule.
MAX_PERIOD_DAYS = 366

# How many dates one solve covers. Four weeks is a whole roster month in
# one model, where fairness and runs of days are seen at once; a longer
# period is solved in such blocks, each seeing the ones before it.
SPAN_DAYS = 28


def build_slots(profile: dict, starts_on: str, ends_on: str) -> List[dict]:
    """One slot per shift per day the shift actually runs.

    A shift with no `days` runs every day — setup leaves it empty to
    confirm the days, so an empty list means "not restricted" rather than
    "never", and treating it as "never" would produce an empty schedule from
    a profile that looks complete.
    """
    start, end = parse_date(starts_on), parse_date(ends_on)
    if start is None or end is None:
        raise AgentError("תאריכי התקופה אינם תקינים")
    if end < start:
        raise AgentError("תאריך הסיום מוקדם מתאריך ההתחלה")
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        raise AgentError("התקופה ארוכה מדי לבניית סידור אחד")
    shifts = named((profile or {}).get("shifts"))
    return [
        _slot(shift, day, hebrew_weekday(day))
        for day in dates_between(start, end)
        for shift in shifts
        if runs_on(shift.get("days"), hebrew_weekday(day))
    ]


def _slot(shift: dict, day, weekday: str) -> dict:
    headcount, required_roles = staffing_requirements(shift, weekday)
    return {
        "shift_name": bounded(shift.get("name")),
        "slot_date": day.isoformat(),
        "weekday": weekday,
        "start_time": bounded(shift.get("start_time")),
        "end_time": bounded(shift.get("end_time")),
        "headcount": headcount,
        "required_roles": required_roles,
        "requires_shift_manager": bool(shift.get("requires_shift_manager")),
        "is_on_call": bool(shift.get("is_on_call")),
        "is_night": bool(shift.get("is_night") or shift.get("is_overnight")),
        "hour_weight": shift.get("hour_weight", 1.0),
    }


def staffing_requirements(shift: dict, weekday: str) -> tuple:
    """How many people and which roles this shift needs on this weekday.

    `staffing` is per group of days because setup records whether the
    standard changes across the week. A group naming this weekday wins over
    the group naming none, which is the default.
    """
    staffing = shift.get("staffing")
    if not isinstance(staffing, list):
        return 1, []
    fallback = (1, [])
    for group in staffing:
        if not isinstance(group, dict):
            continue
        headcount = group.get("headcount")
        if not isinstance(headcount, int) or isinstance(headcount, bool):
            continue
        days = group.get("days")
        requirement = (headcount, role_list(group.get("required_roles")))
        if not isinstance(days, list) or not days:
            fallback = requirement
        elif runs_on(days, weekday):
            return requirement
    return fallback


def plan_spans(profile: dict, starts_on: str, ends_on: str) -> List[dict]:
    """The date ranges a build is solved in, as `{"date", "through",
    "dates"}`, because progress is counted in dates."""
    dates = sorted({slot["slot_date"] for slot in build_slots(profile, starts_on, ends_on)})
    return [
        {"date": block[0], "through": block[-1], "dates": block}
        for block in (dates[index:index + SPAN_DAYS] for index in range(0, len(dates), SPAN_DAYS))
    ]
