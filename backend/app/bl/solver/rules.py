"""The workplace's own rules: seats, roles, the shift manager, rest, runs
of days and weekly hours.

These are the audit's blocking checks (`bl/audit/`) stated as constraints,
read from the same `policy()` thresholds, so a solved schedule is clean by
the same arithmetic that grades it. A seat nobody can legally take is the
one thing that stays priced rather than forbidden: an unfilled shift is
reported, never refused.

`rest_pairs` and `day_windows` are shared with the structured requests
(`requests.py`), which narrow them by person and by shift.
"""

import datetime
from typing import Callable, Iterator, List, Optional, Tuple

from app.bl.audit import counts_toward_staffing
from app.bl.audit.roster import iso_week
from app.bl.audit.values import number
from app.bl.solver.model import HOUR_SCALE, MISSING_ROLE, UNFILLED, Model
from app.bl.solver.rows import roles

# Two shifts further apart than this cannot be short of any rest we model.
_REST_HORIZON = datetime.timedelta(hours=96)


def apply_rules(model: Model) -> None:
    problem = model.problem
    for index in range(len(problem.slots)):
        _seats(model, index)
        _roles(model, index)
    for name in problem.staff:
        for first, second in rest_pairs(problem, model, name, problem.policy["min_rest_hours"]):
            _forbid_pair(model, first, second)
        for variables, fixed in day_windows(problem, model, name, problem.policy["max_consecutive_days"]):
            model.at_most(variables, problem.policy["max_consecutive_days"] - fixed)
        _weekly_hours(model, name)


def _seats(model: Model, index: int) -> None:
    problem, slot = model.problem, model.problem.slots[index]
    fixed = sum(counts_toward_staffing(problem.people.get(row["employee"]), problem.profile)
                for row in problem.fixed_on(index))
    open_seats = max(0, int(slot.get("headcount") or 0) - fixed)
    placed = model.on_slot(index)
    model.at_most(placed, open_seats)
    if open_seats:
        model.price(UNFILLED, open_seats - sum(placed),
                    "לא נמצא שיבוץ חוקי ל%s בתאריך %s; המשמרת נשארה בחוסר."
                    % (slot["shift_name"], slot["slot_date"]), kind="unfilled")


def _roles(model: Model, index: int) -> None:
    problem, slot = model.problem, model.problem.slots[index]
    fixed = [problem.people.get(row["employee"], {}) for row in problem.fixed_on(index)]
    present = set()
    for person in fixed:
        if counts_toward_staffing(person, problem.profile):
            present.update(roles(person))
    for role in slot.get("required_roles") or []:
        if role not in present:
            holders = model.on_slot(index, problem.holders(index, lambda p, r=role: r in roles(p)))
            covered = model.bool_or(holders, "role_%d" % index)
            model.price(MISSING_ROLE, 1 - covered, "", kind="role")
    if slot.get("requires_shift_manager") and not any(p.get("is_shift_manager") for p in fixed):
        managers = model.on_slot(index, problem.holders(index, lambda p: bool(p.get("is_shift_manager"))))
        covered = model.bool_or(managers, "manager_%d" % index)
        model.price(MISSING_ROLE, 1 - covered, "", kind="manager")


# -- rest ------------------------------------------------------------------


def rest_pairs(problem, model: Model, name: str, minimum: float,
               test: Optional[Callable[[dict, dict], bool]] = None) -> Iterator[Tuple]:
    """Pairs of this person's shifts closer than `minimum` hours. Each side
    is a placement variable or None for a fixed row; two fixed rows are
    already history and are skipped."""
    items = _timed(problem, model, name)
    for position, (earlier, first) in enumerate(items):
        for later, second in items[position + 1:]:
            if later["begins"] - earlier["begins"] > _REST_HORIZON:
                break
            if first is None and second is None:
                continue
            gap = (later["begins"] - earlier["ends"]).total_seconds() / 3600.0
            if gap < minimum and (test is None or test(earlier, later)):
                yield first, second


def _timed(problem, model: Model, name: str) -> List[Tuple[dict, object]]:
    items = [(row, None) for row in problem.fixed
             if row["employee"] == name and row["begins"] is not None]
    for index, var in model.of_person(name).items():
        times = problem.times[index]
        if times["begins"] is not None:
            slot = problem.slots[index]
            items.append((dict(times, shift=slot["shift_name"], date=slot["slot_date"]), var))
    return sorted(items, key=lambda item: (item[0]["begins"], item[0]["ends"]))


def _forbid_pair(model: Model, first, second) -> None:
    if first is None:
        model.cp.Add(second == 0)
    elif second is None:
        model.cp.Add(first == 0)
    else:
        model.cp.Add(first + second <= 1)


# -- runs of days ----------------------------------------------------------


def day_windows(problem, model: Model, name: str, limit: int,
                test: Optional[Callable[[str, str], bool]] = None) -> Iterator[Tuple[list, int]]:
    """Every `limit + 1`-day window touching the period: the worked-day
    flags inside it and how many of its days are already fixed as worked."""
    if limit <= 0 or not problem.dates:
        return
    fixed_days = {row["date"] for row in problem.fixed if row["employee"] == name
                  and (test is None or test(row["shift"], row["date"]))}
    flags = {}
    for day in problem.dates:
        if day in fixed_days:
            continue
        if test is None:
            flag = model.worked(name, day)
        else:
            placed = [var for index, var in model.of_person(name).items()
                      if problem.slots[index]["slot_date"] == day
                      and test(problem.slots[index]["shift_name"], day)]
            flag = model.bool_or(placed, "day") if placed else None
        if flag is not None:
            flags[day] = flag
    first = datetime.date.fromisoformat(problem.dates[0])
    last = datetime.date.fromisoformat(problem.dates[-1])
    start = first - datetime.timedelta(days=limit)
    while start <= last:
        days = [(start + datetime.timedelta(days=step)).isoformat() for step in range(limit + 1)]
        variables = [flags[day] for day in days if day in flags]
        if variables:
            yield variables, sum(day in fixed_days for day in days)
        start += datetime.timedelta(days=1)


# -- hours -----------------------------------------------------------------


def _weekly_hours(model: Model, name: str) -> None:
    problem = model.problem
    limit = number(problem.people[name].get("max_weekly_hours"), 0.0) \
        or problem.policy["max_weekly_hours"]
    weeks = {}
    for index, var in model.of_person(name).items():
        day = datetime.date.fromisoformat(problem.slots[index]["slot_date"])
        weeks.setdefault(iso_week(day), []).append((_tenths(problem.times[index]["hours"]), var))
    for week, placed in weeks.items():
        fixed = sum(_tenths(row["hours"]) for row in problem.fixed if row["employee"] == name
                    and iso_week(datetime.date.fromisoformat(row["date"])) == week)
        model.at_most([var for _, var in placed], _tenths(limit) - fixed,
                      scale=[hours for hours, _ in placed])


def _tenths(hours: float) -> int:
    return int(round(float(hours or 0.0) * HOUR_SCALE))


__all__ = ["apply_rules", "day_windows", "rest_pairs"]
