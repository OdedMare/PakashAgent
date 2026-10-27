"""How the load is shared: closers on their own closure, an even number of
shifts and of nights, and as long a rest between shifts as the roster allows.

Load is counted in shifts, not hours. On base nobody is on the clock — a
soldier is in from Thursday to Sunday and closes the weekend — so what is
owed evenly is the number of shifts, and what is worth winning beyond that
is the gap between them: every pair of one person's shifts closer than
`SPACING_HOURS` pays per hour it is short, which is the sleep the second
shift takes away.

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

from app.bl.solver.model import (
    BACK_TO_BACK, CLOSER, NIGHT_PEAK, NIGHT_SCALE, NIGHT_SPREAD, SHIFT_PEAK, SHIFT_SCALE,
    SHIFT_SPREAD, SPACING, SPACING_HOURS, Model,
)
from app.bl.solver.rules import timed_pairs


def apply_fairness(model: Model) -> None:
    _closers(model)
    shifts = lambda times: SHIFT_SCALE
    _spread(model, shifts, SHIFT_SPREAD, SHIFT_PEAK, "shifts")
    nights = lambda times: NIGHT_SCALE * int(bool(times["night"]))
    _spread(model, nights, NIGHT_SPREAD, NIGHT_PEAK, "nights")
    clocked = any(times["begins"] is not None for times in model.problem.times)
    for name in model.problem.people:
        if clocked:
            _spacing(model, name)
        else:
            _back_to_back(model, name)


def _closers(model: Model) -> None:
    problem = model.problem
    for (name, index), var in sorted(model.x.items()):
        if problem.people[name].get("rotation_group") and problem.closes(name, index):
            model.price(-CLOSER, var, kind="closer")


def _spread(model: Model, measure, weight: int, peak: int, label: str) -> None:
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
    room = {name: _capacity(problem, name, placed, measure)
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


def _capacity(problem, name: str, placed, measure) -> int:
    """About the most this person can still take: the heaviest legal slot
    of each day (rest rarely allows two). An estimate, not a promise; the
    rules decide the rest."""
    days: Dict[str, int] = {}
    for index in placed:
        day = problem.slots[index]["slot_date"]
        days[day] = max(days.get(day, 0), measure(problem.times[index]))
    return sum(days.values())


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


def _spacing(model: Model, name: str) -> None:
    """Pay for every two of this person's shifts closer than `SPACING_HOURS`,
    by the square of the hours short (`model.py`). A pair closer than the
    minimum rest is already forbidden (`rules.py`); this ranks the legal
    ones, longest and most even rest first."""
    horizon = datetime.timedelta(hours=SPACING_HOURS)
    for _, first, _, second, gap in timed_pairs(model.problem, model, name, horizon):
        short = SPACING_HOURS - max(0.0, gap)
        cost = int(round(SPACING * short * short / SPACING_HOURS))
        if cost <= 0:
            continue
        if first is None or second is None:
            both = second if first is None else first
        else:
            both = model.cp.NewBoolVar("close")
            model.cp.Add(both >= first + second - 1)
        model.price(cost, both, kind="spacing")


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
