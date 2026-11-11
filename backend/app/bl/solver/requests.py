"""Structured requests (`bl/schedule_requests.py`) and soft availability.

A hard request is a constraint; a soft one is priced at `WISH` times its
weight, and a `prefer` is the same price as a reward. A hard `avoid` never
reaches here: `Problem` already left those placements out. Rows already
fixed in the draft count toward a limit the way the draft's own rows do;
history counts only where time does (rest and runs of days).
"""

from typing import List

from app.bl.audit import constraint_conflicts
from app.bl.schedule_requests import concerns, covers, week_of
from app.bl.solver.model import WISH, Model
from app.bl.solver.rules import day_windows, rest_pairs

_BROKEN = "%s שובץ/ה ב%s בתאריך %s למרות בקשה רכה: %s."
_PARTLY = "בקשה רכה לא כובדה במלואה: %s."


def apply_requests(model: Model) -> None:
    for request in model.problem.requests:
        _HANDLERS[request["kind"]](model, request)
    _soft_availability(model)


def _price(request: dict) -> int:
    return int(round(WISH * request["weight"]))


def _concerned(model: Model, request: dict) -> List[tuple]:
    """(name, slot index, variable) for every placement the request speaks about."""
    problem = model.problem
    return [(name, index, var) for (name, index), var in sorted(model.x.items())
            if concerns(request, name) and covers(
                request, problem.slots[index]["shift_name"], problem.slots[index]["slot_date"])]


def _fixed_concerned(model: Model, request: dict) -> List[dict]:
    return [row for row in model.problem.fixed if not row["past"]
            and concerns(request, row["employee"]) and covers(request, row["shift"], row["date"])]


def _avoid(model: Model, request: dict) -> None:
    for name, index, var in _concerned(model, request):
        slot = model.problem.slots[index]
        model.price(_price(request), var, _BROKEN % (
            name, slot["shift_name"], slot["slot_date"], request["reason"]), kind="wish")


def _prefer(model: Model, request: dict) -> None:
    for _, _, var in _concerned(model, request):
        model.price(-_price(request), var, kind="prefer")


def _max_count(model: Model, request: dict) -> None:
    groups = {}
    for _, index, var in _concerned(model, request):
        groups.setdefault(_group(request, model.problem.slots[index]["slot_date"]), []).append(var)
    for key, variables in groups.items():
        fixed = sum(_group(request, row["date"]) == key for row in _fixed_concerned(model, request))
        _limit(model, request, variables, request["count"] - fixed)


def _group(request: dict, day: str):
    return week_of(day) if request["per"] == "week" else None


def _not_together(model: Model, request: dict) -> None:
    problem = model.problem
    for index, slot in enumerate(problem.slots):
        if not covers(request, slot["shift_name"], slot["slot_date"]):
            continue
        fixed = sum(row["employee"] in request["employees"] for row in problem.fixed_on(index))
        _limit(model, request, model.on_slot(index, request["employees"]), 1 - fixed)


def _limit(model: Model, request: dict, variables: list, limit: int) -> None:
    if request["is_hard"]:
        model.at_most(variables, limit)
    else:
        model.price_excess(variables, limit, _price(request), _PARTLY % request["reason"], "wish")


def _min_rest(model: Model, request: dict) -> None:
    problem = model.problem
    scope = dict(request, shifts=[])

    def matters(earlier: dict, later: dict) -> bool:
        if request["shifts"] and earlier["shift"] not in request["shifts"] \
                and later["shift"] not in request["shifts"]:
            return False
        return covers(scope, later["shift"], later["date"]) or covers(scope, earlier["shift"], earlier["date"])

    for name in problem.people:
        if not concerns(request, name):
            continue
        for first, second in rest_pairs(problem, model, name, request["count"], matters):
            _pair(model, request, first, second)


def _pair(model: Model, request: dict, first, second) -> None:
    if first is None or second is None:
        alone = first if second is None else second
        if request["is_hard"]:
            model.cp.Add(alone == 0)
        else:
            model.price(_price(request), alone, _PARTLY % request["reason"], "wish")
        return
    if request["is_hard"]:
        model.cp.Add(first + second <= 1)
        return
    both = model.cp.NewBoolVar("rest")
    model.cp.Add(both >= first + second - 1)
    model.price(_price(request), both, _PARTLY % request["reason"], "wish")


def _max_consecutive(model: Model, request: dict) -> None:
    problem = model.problem
    for name in problem.people:
        if not concerns(request, name):
            continue
        windows = day_windows(problem, model, name, request["count"],
                              lambda shift, day: covers(request, shift, day))
        for variables, fixed in windows:
            _limit(model, request, variables, request["count"] - fixed)


def _balance(model: Model, request: dict) -> None:
    problem = model.problem
    group = request["employees"] or problem.staff
    counts = {name: [] for name in group}
    for name, _, var in _concerned(model, request):
        if name in counts:
            counts[name].append(var)
    fixed = _fixed_concerned(model, request)
    totals = []
    for name, variables in counts.items():
        total = model.cp.NewIntVar(0, len(problem.slots) + len(fixed), "share")
        model.cp.Add(total == sum(variables) + sum(row["employee"] == name for row in fixed))
        totals.append(total)
    if len(totals) < 2:
        return
    most = model.cp.NewIntVar(0, len(problem.slots) + len(fixed), "most")
    least = model.cp.NewIntVar(0, len(problem.slots) + len(fixed), "least")
    model.cp.AddMaxEquality(most, totals)
    model.cp.AddMinEquality(least, totals)
    model.price(_price(request), most - least, kind="balance")


def _requires_with(model: Model, request: dict) -> None:
    problem = model.problem
    for name, index, var in _concerned(model, request):
        if any(row["employee"] in request["partners"] for row in problem.fixed_on(index)):
            continue
        partners = sum(model.on_slot(index, request["partners"]))
        if request["is_hard"]:
            model.cp.Add(var <= partners)
            continue
        alone = model.cp.NewBoolVar("alone")
        model.cp.Add(alone >= var - partners)
        slot = problem.slots[index]
        model.price(_price(request), alone, _BROKEN % (
            name, slot["shift_name"], slot["slot_date"], request["reason"]), kind="wish")


def _soft_availability(model: Model) -> None:
    problem = model.problem
    if not problem.soft:
        return
    for (name, index), var in sorted(model.x.items()):
        candidate = problem.candidate(name, index)
        for item in problem.soft:
            if constraint_conflicts(candidate, item):
                slot = problem.slots[index]
                model.price(WISH, var, _BROKEN % (
                    name, slot["shift_name"], slot["slot_date"],
                    item.get("reason") or "אילוץ זמינות רך"), kind="wish")


_HANDLERS = {
    "avoid": _avoid, "prefer": _prefer, "max_count": _max_count,
    "not_together": _not_together, "min_rest": _min_rest,
    "max_consecutive": _max_consecutive, "balance": _balance,
    "requires_with": _requires_with,
}


__all__ = ["apply_requests"]
