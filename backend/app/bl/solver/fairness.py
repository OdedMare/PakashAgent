"""How the load is shared: closers on their own closure, even hours, even
nights, and a day off between shifts where the roster allows one.

Evenness is the L1 distance of each person's load from an even share of
the demand, multiplied through by the team size so it stays integer. The load counts
the rows already fixed (the rest of the draft and the last two weeks), so a
day rebuilt inside a period, or a period following a heavy one, leans away
from whoever already carries more. People with no legal placement and
nothing fixed take no part in the mean.
"""

import datetime

from app.bl.solver.model import BACK_TO_BACK, CLOSER, HOUR_SCALE, HOUR_SPREAD, NIGHT_SPREAD, Model


def apply_fairness(model: Model) -> None:
    _closers(model)
    _spread(model, lambda times: int(round(times["hours"] * HOUR_SCALE)), HOUR_SPREAD, "hours")
    _spread(model, lambda times: int(bool(times["night"])), NIGHT_SPREAD, "nights")
    for name in model.problem.staff:
        _back_to_back(model, name)


def _closers(model: Model) -> None:
    problem = model.problem
    for (name, index), var in sorted(model.x.items()):
        if problem.people[name].get("rotation_group") and problem.closes(name, index):
            model.price(-CLOSER, var, kind="closer")


def _spread(model: Model, measure, weight: int, label: str) -> None:
    """L1 distance of each load from an even share of the whole demand.

    The share is a constant worked out before solving (every seat times its
    measure, plus what is already fixed), not the mean of the solution: a
    target that moves with the answer couples everyone to everyone and the
    solver can no longer prove a schedule optimal."""
    problem = model.problem
    loads = {}
    for name in problem.staff:
        placed = model.of_person(name)
        fixed = sum(measure(row) for row in problem.fixed if row["employee"] == name)
        if placed or fixed:
            loads[name] = (placed, fixed)
    if len(loads) < 2:
        return
    team = len(loads)
    demand = sum(measure(times) * max(0, int(slot.get("headcount") or 0))
                 for times, slot in zip(problem.times, problem.slots))
    demand += sum(measure(row) for row in problem.fixed if row["employee"] in loads)
    bound = team * demand + demand + 1
    for name, (placed, fixed) in loads.items():
        load = sum(measure(problem.times[index]) * var for index, var in placed.items()) + fixed
        distance = model.cp.NewIntVar(0, bound, "%s_%s" % (label, len(model.terms)))
        model.cp.Add(distance >= team * load - demand)
        model.cp.Add(distance >= demand - team * load)
        model.price(weight, distance, kind=label)


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
