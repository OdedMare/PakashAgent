"""The slot grid, and how it is divided into model calls.

Built in code rather than asked of the model: which dates fall in a period and
which weekday each one is is arithmetic, and the model has no business
generating a calendar. It assigns people into this grid.
"""

from typing import Dict, List

from app.bl.hebrew_calendar import hebrew_weekday, runs_on
from app.bl.scheduler.values import (
    bounded, dates_between, named, parse_date, role_list,
)
from app.common.config.settings import MODE_DAY, MODE_WEEK
from app.common.errors import AgentError

# Checkpointed daily generation makes long planning horizons safe to resume.
# One leap year is a useful product ceiling; beyond that belongs in a separate
# forecast rather than one living operational schedule.
MAX_PERIOD_DAYS = 366

# A period is built in bounded chunks. Seven days is the calendar ceiling,
# while staffing volume is the output ceiling: a busy week can require far
# more JSON rows than a quiet fortnight, and small models otherwise tend to
# answer only the first day while still returning valid JSON.
CHUNK_DAYS = 7
MAX_ASSIGNMENTS_PER_CHUNK = 14

# The staffing demand one span may carry in week mode. Far above the chunk
# limit because the span path's response schema pins every row to an
# enumerated slot and an enumerated candidate -- the ceiling is about how much
# one answer can hold, not about how much can be trusted. A week that needs
# more is split, which is why week mode is a ceiling rather than a promise.
MAX_ASSIGNMENTS_PER_SPAN = 70


def build_slots(profile: dict, starts_on: str, ends_on: str) -> List[dict]:
    """One slot per shift per day the shift actually runs.

    A shift with no `days` runs every day — the interview is instructed to
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
    }


def staffing_requirements(shift: dict, weekday: str) -> tuple:
    """How many people and which roles this shift needs on this weekday.

    `staffing` is per group of days because the interview asks whether the
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


def chunks(
    slots: List[dict], demand_limit: int = MAX_ASSIGNMENTS_PER_CHUNK
) -> List[List[dict]]:
    """Split the grid without dividing a day or overloading one model call.

    Split on dates rather than on slot count, so a day is never divided across
    two calls: half a Tuesday in one request and half in another is how the
    same person ends up on two shifts at once. Staffing headcount, not slot
    count, estimates the rows the model must return.
    """
    by_date: Dict[str, List[dict]] = {}
    for slot in slots:
        by_date.setdefault(slot["slot_date"], []).append(slot)
    result: List[List[dict]] = []
    chunk: List[dict] = []
    demand = days = 0
    for date in sorted(by_date):
        day_slots = by_date[date]
        day_demand = sum(max(1, slot.get("headcount", 1)) for slot in day_slots)
        if chunk and (days >= CHUNK_DAYS or demand + day_demand > demand_limit):
            result.append(chunk)
            chunk, demand, days = [], 0, 0
        chunk.extend(day_slots)
        demand += day_demand
        days += 1
    if chunk:
        result.append(chunk)
    return result


def plan_spans(
    profile: dict, starts_on: str, ends_on: str, mode: str = MODE_DAY
) -> List[dict]:
    """The date ranges a range job will ask the model for, one call each.

    Returned as `{"date", "through", "dates"}` because the caller counts
    progress in *dates* however wide a call is. In day mode every span is one
    date; in week mode `chunks` bounds it, so a span never crosses seven days
    and a week whose demand would not fit one answer is split.
    """
    slots = build_slots(profile, starts_on, ends_on)
    if mode != MODE_WEEK:
        return [
            {"date": date, "through": date, "dates": [date]}
            for date in sorted({slot["slot_date"] for slot in slots})
        ]
    spans = []
    for chunk in chunks(slots, MAX_ASSIGNMENTS_PER_SPAN):
        dates = sorted({slot["slot_date"] for slot in chunk})
        spans.append({"date": dates[0], "through": dates[-1], "dates": dates})
    return spans
