"""Reservists' days a week, and shifts balanced by competence.

**A reservist comes a stated number of days a week.** `reserve_days_per_week`
on a `service_type: reserve` soldier is a hard cap on the days they work in
each Sunday–Saturday week, counting the days already fixed in it (the rest
of the draft, the last two weeks). Like every other hard rule here, a limit
made negative by fixed rows is clamped at zero, so the model stays feasible.

**A shift should not be staffed only by the weakest.** `competence` is an
optional rating — weak, medium, high, excellent — and when the roster rates
people at more than one level, each slot with two or more seats is pulled
towards the team's average strength: a shortfall below it is priced four
times an excess over it, so the solver spreads strong soldiers across shifts
rather than stacking them, and two weak soldiers on one shift pay extra.
An unrated soldier counts as the team's average and moves nothing.

Both prices sit below a soft wish and around one shift of evenness
(`model.py`): balance is worth a shift moving, not a broken request.
"""

import datetime
from typing import Dict, List, Optional, Tuple

from app.bl.audit import counts_toward_staffing
from app.bl.solver.model import Model
from app.bl.solver.rows import text

# Rating → strength, in tenths so an unrated soldier can sit at the mean.
LEVELS = {"weak": 10, "medium": 20, "high": 30, "excellent": 40}
# Per tenth of a level: a slot short of the average strength, and one above it.
BELOW_AVERAGE = 4
ABOVE_AVERAGE = 1
# Each weak soldier past the first on one shift.
WEAK_TOGETHER = 150


def apply_competence(model: Model) -> None:
    for name in model.problem.people:
        _reserve_days(model, name)
    _balance(model)


# -- reservists ------------------------------------------------------------


def reserve_days(person: dict) -> Optional[int]:
    """The days a week this person comes, or None when nothing caps them."""
    if text(person.get("service_type")) != "reserve":
        return None
    try:
        days = int(person.get("reserve_days_per_week") or 0)
    except (TypeError, ValueError):
        return None
    return days if 1 <= days <= 7 else None


def week_of(day: str) -> str:
    """The Sunday that opens the Israeli week holding `day`."""
    date = datetime.date.fromisoformat(day)
    return (date - datetime.timedelta(days=(date.weekday() + 1) % 7)).isoformat()


def _reserve_days(model: Model, name: str) -> None:
    problem = model.problem
    limit = reserve_days(problem.people[name])
    if limit is None:
        return
    fixed: Dict[str, set] = {}
    for row in problem.fixed:
        if row["employee"] == name:
            fixed.setdefault(week_of(row["date"]), set()).add(row["date"])
    weeks: Dict[str, List] = {}
    for day in problem.dates:
        if day in fixed.get(week_of(day), set()):
            continue
        flag = model.worked(name, day)
        if flag is not None:
            weeks.setdefault(week_of(day), []).append(flag)
    for week, flags in weeks.items():
        model.at_most(flags, limit - len(fixed.get(week, set())))


# -- competence ------------------------------------------------------------


def strengths(problem) -> Optional[Tuple[Dict[str, int], int]]:
    """Each counted person's strength and the team's mean, or None when
    fewer than two levels are rated and there is nothing to balance."""
    rated = {name: LEVELS[text(problem.people[name].get("competence"))]
             for name in problem.staff
             if text(problem.people[name].get("competence")) in LEVELS}
    if len(set(rated.values())) < 2:
        return None
    mean = int(round(sum(rated.values()) / float(len(rated))))
    return {name: rated.get(name, mean) for name in problem.staff}, mean


def _balance(model: Model) -> None:
    problem = model.problem
    found = strengths(problem)
    if found is None:
        return
    strength, mean = found
    weak = LEVELS["weak"]
    for index, slot in enumerate(problem.slots):
        seats = int(slot.get("headcount") or 0)
        if seats < 2:
            continue
        fixed = [row["employee"] for row in problem.fixed_on(index)
                 if counts_toward_staffing(problem.people.get(row["employee"]), problem.profile)]
        placed = {name: var for name, var in model.by_slot.get(index, {}).items()
                  if name in strength}
        if not placed:
            continue
        total = sum(strength[name] * var for name, var in placed.items()) \
            + sum(strength.get(name, mean) for name in fixed)
        target = mean * seats
        top = max(LEVELS.values()) * seats
        short = model.cp.NewIntVar(0, top, "competence_short_%d" % index)
        over = model.cp.NewIntVar(0, top, "competence_over_%d" % index)
        model.cp.Add(short >= target - total)
        model.cp.Add(over >= total - target)
        model.price(BELOW_AVERAGE, short, kind="competence")
        model.price(ABOVE_AVERAGE, over, kind="competence")
        weak_fixed = sum(1 for name in fixed if strength.get(name) == weak)
        weak_placed = [var for name, var in placed.items() if strength[name] == weak]
        model.price_excess(weak_placed, max(0, 1 - weak_fixed), WEAK_TOGETHER, "", kind="competence")


__all__ = ["LEVELS", "apply_competence", "reserve_days", "strengths", "week_of"]
