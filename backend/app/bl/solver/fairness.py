"""How the load is shared: closers on their own closure, even hours, even
nights, and a day off between shifts where the roster allows one.

Each person's load is driven towards a target of their own: the demand
poured evenly over the team, but no one is asked for less than they
already carry nor more than they can take (water-filling). So a part-timer
or someone mostly unavailable is not counted at an even share they cannot
reach, which would hand the remainder to the others unweighed. Two prices
pull towards the targets: the L1 distance of every load from its target,
and the largest overload of anyone, so the excess is shared rather than
left with whoever a small wish pointed at.

Targets are constants worked out before solving, not the mean of the
solution: a target that moves with the answer couples everyone to everyone
and the solver can no longer prove a schedule optimal. Prices are per unit
of load and do not grow with the team, so one shift of evenness stays
cheaper than a soft wish however large the team is (`model.py`).

The load counts the rows already fixed (the rest of the draft and the last
two weeks), so a day rebuilt inside a period, or a period following a heavy
one, leans away from whoever already carries more. People with no legal
placement and nothing fixed take no part.
"""

import datetime
from typing import Dict, List

from app.bl.audit.roster import iso_week
from app.bl.audit.values import number
from app.bl.solver.model import (
    BACK_TO_BACK, CLOSER, HOUR_PEAK, HOUR_SCALE, HOUR_SPREAD, NIGHT_PEAK, NIGHT_SCALE,
    NIGHT_SPREAD, Model,
)


def apply_fairness(model: Model) -> None:
    _closers(model)
    hours = lambda times: int(round(times["hours"] * HOUR_SCALE))
    _spread(model, hours, HOUR_SPREAD, HOUR_PEAK, "hours", _weekly_limit(model.problem))
    nights = lambda times: NIGHT_SCALE * int(bool(times["night"]))
    _spread(model, nights, NIGHT_SPREAD, NIGHT_PEAK, "nights")
    for name in model.problem.staff:
        _back_to_back(model, name)


def _closers(model: Model) -> None:
    problem = model.problem
    for (name, index), var in sorted(model.x.items()):
        if problem.people[name].get("rotation_group") and problem.closes(name, index):
            model.price(-CLOSER, var, kind="closer")


def _spread(model: Model, measure, weight: int, peak: int, label: str, weekly=None) -> None:
    problem = model.problem
    loads = {}
    for name in problem.staff:
        placed = model.of_person(name)
        fixed = sum(measure(row) for row in problem.fixed if row["employee"] == name)
        if placed or fixed:
            loads[name] = (placed, fixed)
    if len(loads) < 2:
        return
    demand = sum(measure(times) * max(0, int(slot.get("headcount") or 0))
                 for times, slot in zip(problem.times, problem.slots))
    demand += sum(fixed for _, fixed in loads.values())
    room = {name: _capacity(problem, name, placed, measure, weekly)
            for name, (placed, _) in loads.items()}
    targets = water_fill({name: fixed for name, (_, fixed) in loads.items()}, room, demand)
    top = demand + max(fixed for _, fixed in loads.values()) + 1
    worst = model.cp.NewIntVar(0, top, "%s_peak" % label)
    for name, (placed, fixed) in loads.items():
        load = sum(measure(problem.times[index]) * var for index, var in placed.items()) + fixed
        distance = model.cp.NewIntVar(0, top, "%s_%s" % (label, len(model.terms)))
        model.cp.Add(distance >= load - targets[name])
        model.cp.Add(distance >= targets[name] - load)
        model.cp.Add(worst >= load - targets[name])
        model.price(weight, distance, kind=label)
    model.price(peak, worst, kind=label)


def _capacity(problem, name: str, placed, measure, weekly) -> int:
    """About the most this person can still take: the heaviest legal slot
    of each day (rest rarely allows two), held under the weekly limit when
    one is given. An estimate, not a promise; the rules decide the rest."""
    days: Dict[str, int] = {}
    for index in placed:
        day = problem.slots[index]["slot_date"]
        days[day] = max(days.get(day, 0), measure(problem.times[index]))
    if weekly is None:
        return sum(days.values())
    weeks: Dict[tuple, int] = {}
    for day, amount in days.items():
        week = iso_week(datetime.date.fromisoformat(day))
        weeks[week] = weeks.get(week, 0) + amount
    return sum(min(amount, max(0, weekly(name, week))) for week, amount in weeks.items())


def _weekly_limit(problem):
    """Tenths of an hour `name` may still work in `week`, as `rules.py` caps it."""
    def left(name: str, week: tuple) -> int:
        limit = number(problem.people[name].get("max_weekly_hours"), 0.0) \
            or problem.policy["max_weekly_hours"]
        fixed = sum(row["hours"] for row in problem.fixed if row["employee"] == name
                    and iso_week(datetime.date.fromisoformat(row["date"])) == week)
        return int(round((limit - fixed) * HOUR_SCALE))
    return left


def water_fill(floors: Dict[str, int], room: Dict[str, int], demand: int) -> Dict[str, int]:
    """Pour `demand` evenly: everyone reaches one common level, but no one
    falls below their floor (what they already carry) or rises above floor
    plus room (what they can take). Integer targets summing to `demand`
    whenever the floors and ceilings allow it."""
    names = sorted(floors)
    ceilings = {name: floors[name] + max(0, room.get(name, 0)) for name in names}
    low, high = min(floors.values()), max(ceilings.values())

    def poured(level: float) -> float:
        return sum(min(ceilings[name], max(floors[name], level)) for name in names)

    if poured(high) <= demand:
        return dict(ceilings)
    for _ in range(64):
        middle = (low + high) / 2.0
        if poured(middle) < demand:
            low = middle
        else:
            high = middle
    exact = {name: min(ceilings[name], max(floors[name], high)) for name in names}
    targets = {name: int(exact[name]) for name in names}
    # Hand the rounding remainder to the largest fractions, within ceilings.
    short = int(round(sum(exact.values()))) - sum(targets.values())
    order: List[str] = sorted(names, key=lambda name: (targets[name] - exact[name], name))
    for name in order:
        if short <= 0:
            break
        if targets[name] < ceilings[name]:
            targets[name] += 1
            short -= 1
    return targets


def _back_to_back(model: Model, name: str) -> None:
    problem = model.problem
    if not problem.dates:
        return
    worked = {row["date"] for row in problem.fixed if row["employee"] == name}
    days = {day: model.worked(name, day) for day in problem.dates if day not in worked}
    days = {day: flag for day, flag in days.items() if flag is not None}
    for day, flag in days.items():
        yesterday = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
        if yesterday in worked:
            model.price(BACK_TO_BACK, flag, kind="spacing")
        elif yesterday in days:
            both = model.cp.NewBoolVar("pair")
            model.cp.Add(both >= flag + days[yesterday] - 1)
            model.price(BACK_TO_BACK, both, kind="spacing")
        tomorrow = (datetime.date.fromisoformat(day) + datetime.timedelta(days=1)).isoformat()
        if tomorrow in worked:
            model.price(BACK_TO_BACK, flag, kind="spacing")
