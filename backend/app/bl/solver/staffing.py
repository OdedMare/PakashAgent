"""The unit's staffing standard as constraints (`audit/unit_policy.py`).

- **Role seats.** A role listed N times in a slot's `required_roles` needs N
  people holding it, each person filling one seat. A seat nobody holding
  the role can take may go to a holder of one of its fallback roles, at a
  price; a seat still empty is a missing role.
- **The weak.** No more people of competence "weak" on one shift than
  `max_weak_per_shift`. Hard: placing nobody stays feasible.
- **Weekly shifts.** At most `max` shifts per Sunday-to-Saturday week, plus
  the unit's `weekly_shifts_overflow` (hard: past that the seat stays
  empty). Each shift over `max` is priced, so coverage settles first and an
  overflow is taken only for a seat nobody else could fill; its note and the
  audit's warning on that shift say so. At least `min` in every whole week
  of the span (priced, since leave and closures can make it impossible).
"""

import datetime

from app.bl.audit import counts_toward_staffing
from app.bl.audit.unit_policy import (
    cover, fallbacks, held_roles, is_weak, max_weak, role_needs, unit_week, weekly_limits,
    weekly_overflow,
)
from app.bl.solver.model import MISSING_ROLE, Model

# A fallback seat costs more than a soft wish (the unit would rather break
# a "prefers not" than seat the wrong role) and far less than a missing one.
FALLBACK = 3_000
# A week short of its minimum outweighs a wish; it is the unit's standard.
UNDER_MIN = 1_500
# A shift past the weekly maximum, within the allowed overflow: dearer than
# anything but coverage, so it is spent only on a seat that needed it.
OVER_MAX = 10_000


def apply_staffing(model: Model) -> None:
    problem = model.problem
    backups = fallbacks(problem.profile)
    cap = max_weak(problem.profile)
    for index in range(len(problem.slots)):
        _role_seats(model, index, backups)
        if cap is not None:
            _weak_cap(model, index, cap)
    overflow = weekly_overflow(problem.profile)
    for name in problem.staff:
        _weekly_shifts(model, name, overflow)


def _role_seats(model: Model, index: int, backups: dict) -> None:
    problem, slot = model.problem, model.problem.slots[index]
    needs = role_needs(slot.get("required_roles") or [])
    if not needs:
        return
    fixed = [problem.people.get(row["employee"], {}) for row in problem.fixed_on(index)]
    present = [held_roles(person) for person in fixed
               if counts_toward_staffing(person, problem.profile)]
    residual, _ = cover(present, needs, backups)
    if not residual:
        return
    seats = {role: [] for role in residual}
    for name in problem.staff:
        var = model.placed(name, index)
        if var is None:
            continue
        held, chosen = held_roles(problem.people[name]), []
        for role in residual:
            first_hand = role in held
            if not first_hand and not held.intersection(backups.get(role, ())):
                continue
            seat = model.cp.NewBoolVar("seat_%d" % index)
            seats[role].append(seat)
            chosen.append(seat)
            if not first_hand:
                model.price(FALLBACK, seat, "%s מילא/ה את התפקיד %s בעדיפות שנייה (%s, %s)."
                            % (name, role, slot["shift_name"], slot["slot_date"]), kind="fallback")
        if chosen:
            model.cp.Add(sum(chosen) <= var)
    for role, count in residual.items():
        short = model.cp.NewIntVar(0, count, "short_%d" % index)
        model.cp.Add(sum(seats[role]) + short >= count)
        model.price(MISSING_ROLE, short, "חסר/ה %s ב%s בתאריך %s."
                    % (role, slot["shift_name"], slot["slot_date"]), kind="role")


def _weak_cap(model: Model, index: int, cap: int) -> None:
    problem = model.problem
    fixed = sum(1 for row in problem.fixed_on(index)
                if is_weak(problem.people.get(row["employee"])))
    weak = [name for name in problem.people if is_weak(problem.people[name])]
    model.at_most(model.on_slot(index, weak), cap - fixed)


def _weekly_shifts(model: Model, name: str, overflow: int = 0) -> None:
    problem = model.problem
    low, high = weekly_limits(problem.profile, problem.people[name])
    if not low and high is None:
        return
    weeks, days = {}, {}
    for index, var in model.of_person(name).items():
        week = unit_week(datetime.date.fromisoformat(problem.slots[index]["slot_date"]))
        weeks.setdefault(week, []).append(var)
    for day in problem.dates:
        days.setdefault(unit_week(datetime.date.fromisoformat(day)), set()).add(day)
    for week, variables in weeks.items():
        fixed = sum(1 for row in problem.fixed if row["employee"] == name
                    and unit_week(datetime.date.fromisoformat(row["date"])) == week)
        if high is not None:
            model.at_most(variables, high + overflow - fixed)
            if overflow:
                model.price_excess(
                    variables, max(0, high - fixed), OVER_MAX,
                    "%s שובץ/ה מעל המקסימום של %d משמרות בשבוע שמתחיל ב-%s, כדי שמשמרת לא תישאר ריקה."
                    % (name, high, week.isoformat()), kind="over_max")
        wanted = min(low, len(variables)) - fixed
        if wanted > 0 and len(days.get(week, ())) == 7:
            short = model.cp.NewIntVar(0, wanted, "under_%s" % name)
            model.cp.Add(sum(variables) + short >= wanted)
            model.price(UNDER_MIN, short, "%s שובץ/ה בשבוע פחות מהמינימום (%d משמרות)."
                        % (name, low), kind="under_min")
