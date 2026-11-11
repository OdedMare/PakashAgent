"""Reservists' days a week, and shifts balanced by competence.

**A reservist comes a stated number of days a week.** `reserve_days_per_week`
on a `service_type: reserve` soldier is a hard cap on the days they work in
any seven consecutive days, counting the days already fixed in that window
(the rest of the draft, the last two weeks). Like every other hard rule here,
a limit made negative by fixed rows is clamped at zero, so the model stays
feasible. A standard-service officer or NCO (`rank_group`) can be given the
same three fields — five days a week, say — and is held to them the same way.

**A reservist can be owed a minimum, and a block.** `reserve_min_days` is a
soft floor on the same week: each day short of it is priced below a soft
wish and above several shifts of evenness, so a reservist who was called up
is used, but a hard availability or a full board can still leave them short
(and the build says so). It is weighed only on a week the span reaches to
its Saturday; a week cut by the span's end is finished by the next span,
which sees these rows as fixed. `reserve_consecutive` makes the week's
worked days one unbroken block (hard): for any two worked days, every day
between them is worked too. Which days is left to the solver, so a dynamic
reservist is placed where the board needs them.

**A shift should not be staffed only by the weakest.** `competence` is an
optional rating — weak, medium, high, excellent — and when the roster rates
people at more than one level, each slot with two or more seats is pulled
towards the team's average strength: a shortfall below it is priced four
times an excess over it, so the solver spreads strong soldiers across shifts
rather than stacking them, and two weak soldiers on one shift pay extra.
An unrated soldier counts as the team's average and moves nothing.

**A strong shift keeps weaker soldiers off it.** A shift whose definition
names `min_competence` prices every placement of a rated soldier below that
level (`STRONG_SHIFT`), so the solver puts its strong soldiers there first.
A price, not a bar: coverage is solved first, so a seat with no strong
soldier free is still filled — and the audit names who is below the level
on that soldier's own card. An unrated soldier is never below.

Both prices sit below a soft wish and around one shift of evenness
(`model.py`): balance is worth a shift moving, not a broken request.
"""

import datetime
from typing import Dict, List, Optional, Tuple

from app.bl.audit import counts_toward_staffing
from app.bl.audit.unit_policy import below_level, comes_days_a_week, reserve_days
from app.bl.solver.model import Model
from app.bl.shared import switched_off
from app.bl.solver.rows import text

# Rating → strength, in tenths so an unrated soldier can sit at the mean.
LEVELS = {"weak": 10, "medium": 20, "high": 30, "excellent": 40}
# Per tenth of a level: a slot short of the average strength, and one above it.
BELOW_AVERAGE = 4
ABOVE_AVERAGE = 1
# Each weak soldier past the first on one shift.
WEAK_TOGETHER = 150
# Each soldier below a strong shift's level: below a soft wish, above
# several shifts of evenness.
STRONG_SHIFT = 700
# Each day a reservist falls short of their weekly minimum: below a soft wish
# (1000), above several shifts of evenness (10 per tenth of a shift).
RESERVE_SHORT = 600


def apply_competence(model: Model) -> None:
    for name in model.problem.people:
        _reserve_days(model, name)
        _reserve_minimum(model, name)
        _reserve_block(model, name)
    _balance(model)
    _strong_shifts(model)


# -- reservists ------------------------------------------------------------


def reserve_minimum(person: dict) -> Optional[int]:
    """The fewest days a week this reservist should come, or None. A
    reservist switched off (D49) is owed nothing: they are not coming."""
    if not comes_days_a_week(person) or switched_off(person):
        return None
    try:
        days = int(person.get("reserve_min_days") or 0)
    except (TypeError, ValueError):
        return None
    if not 1 <= days <= 7:
        return None
    cap = reserve_days(person)
    return min(days, cap) if cap is not None else days


def reserve_consecutive(person: dict) -> bool:
    return comes_days_a_week(person) and person.get("reserve_consecutive") is True


def week_of(day: str) -> str:
    """The Sunday that opens the Israeli week holding `day`."""
    date = datetime.date.fromisoformat(day)
    return (date - datetime.timedelta(days=(date.weekday() + 1) % 7)).isoformat()


def _reserve_days(model: Model, name: str) -> None:
    problem = model.problem
    limit = reserve_days(problem.people[name])
    if limit is None or not problem.dates:
        return
    fixed = _fixed_days(problem, name)
    flags = {}
    for day in problem.dates:
        if day in fixed:
            continue
        flag = model.worked(name, day)
        if flag is not None:
            flags[day] = flag
    start = datetime.date.fromisoformat(problem.dates[0]) - datetime.timedelta(days=6)
    last = datetime.date.fromisoformat(problem.dates[-1])
    while start <= last:
        window = [(start + datetime.timedelta(days=offset)).isoformat() for offset in range(7)]
        variables = [flags[day] for day in window if day in flags]
        if variables:
            model.at_most(variables, limit - len(fixed.intersection(window)))
        start += datetime.timedelta(days=1)


def _fixed_days(problem, name: str) -> set:
    return {row["date"] for row in problem.fixed if row["employee"] == name}


def _week_dates(sunday: str) -> List[str]:
    start = datetime.date.fromisoformat(sunday)
    return [(start + datetime.timedelta(days=offset)).isoformat() for offset in range(7)]


def _reserve_minimum(model: Model, name: str) -> None:
    problem = model.problem
    least = reserve_minimum(problem.people[name])
    if least is None or not problem.dates:
        return
    fixed = _fixed_days(problem, name)
    last = problem.dates[-1]
    for sunday in sorted({week_of(day) for day in problem.dates}):
        week = _week_dates(sunday)
        if week[-1] > last:
            continue  # the next span finishes this week
        owed = least - len(fixed.intersection(week))
        if owed <= 0:
            continue
        flags = [flag for flag in (model.worked(name, day) for day in week if day not in fixed)
                 if flag is not None]
        short = model.cp.NewIntVar(0, owed, "reserve_short")
        model.cp.Add(short >= owed - sum(flags))
        model.price(RESERVE_SHORT, short,
                    "%s שובץ/ה לפחות מ-%d הימים שלו/ה בשבוע שמתחיל ב-%s" % (name, least, sunday),
                    "reserve")


def _reserve_block(model: Model, name: str) -> None:
    """Hard: the week's worked days have no gap. A day the span does not
    reach is unknown and constrains nothing; two fixed days around a gap no
    variable can close are already decided and are left alone, so the model
    stays feasible."""
    problem = model.problem
    if not reserve_consecutive(problem.people[name]) or not problem.dates:
        return
    fixed = _fixed_days(problem, name)
    first, last = problem.dates[0], problem.dates[-1]
    for sunday in sorted({week_of(day) for day in problem.dates}):
        values = []
        for day in _week_dates(sunday):
            if day in fixed:
                values.append(1)
            elif day > last:
                values.append(None)  # a later span decides it
            else:
                # Before the span and not fixed: not worked. In the span: the flag, or 0.
                flag = model.worked(name, day) if day >= first else None
                values.append(flag if flag is not None else 0)
        for i in range(7):
            for k in range(i + 2, 7):
                ends = (values[i], values[k])
                # Compare by identity: `==` on a CP-SAT variable builds a constraint.
                if any(end is None for end in ends) or all(isinstance(end, int) for end in ends):
                    continue
                for j in range(i + 1, k):
                    middle = values[j]
                    if middle is None or (isinstance(middle, int) and middle == 1):
                        continue
                    model.cp.Add(values[i] + values[k] - 1 <= middle)


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


def _strong_shifts(model: Model) -> None:
    problem = model.problem
    for (name, index), var in sorted(model.x.items()):
        slot = problem.slots[index]
        found = below_level(problem.people.get(name), problem.shifts.get(slot["shift_name"]))
        if found is not None:
            model.price(STRONG_SHIFT, var, _BELOW % (
                name, slot["shift_name"], slot["slot_date"]), kind="competence")


_BELOW = "%s שובץ/ה ל%s ב-%s למרות שהמשמרת דורשת רמה מקצועית גבוהה יותר"


__all__ = ["LEVELS", "apply_competence", "reserve_days", "strengths", "week_of"]
