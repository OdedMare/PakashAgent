"""`Model`: the CP-SAT model, its placement variables and its priced terms.

Every legal (person, slot) pair is one boolean. Hard rules are constraints;
everything else is a `Term` in the objective — a weight, an expression the
solver minimises, and the Hebrew note to write when the solution still pays
for it. A constant on the right-hand side of a hard rule (rows that are
already fixed) is clamped at zero, so placing nobody is always feasible and
the solver can never answer "no schedule exists".
"""

from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

# The objective is lexicographic in spirit: one unfilled seat outweighs any
# number of missing roles, a missing role any number of wishes, and so on.
UNFILLED = 1_000_000
MISSING_ROLE = 100_000
CLOSER = 2_000
WISH = 1_000
SHADOW = 500
# Evenness is priced per unit of load (`fairness.py`) and does not grow with
# the team. Load is counted in shifts, not hours: a soldier on base from
# Thursday to Sunday is not on the clock, and what is fair is an even number
# of shifts. Moving one shift, night included, from the heaviest to the
# lightest saves less than one soft wish, so a wish is never broken for one
# shift of evenness, and more than any one gap between shifts costs.
SHIFT_SPREAD = 10
SHIFT_PEAK = 10
NIGHT_SPREAD = 15
NIGHT_PEAK = 15
# Rest between two shifts of one person is priced by how far short of
# SPACING_HOURS it falls, squared: SPACING * short² / SPACING_HOURS. So among
# even schedules the one with the most rest wins, and a quick turnaround
# (the night's sleep it takes) costs more than two middling gaps — 8 hours
# and 40 cost 138, 24 and 24 cost 96. At most SPACING * SPACING_HOURS a pair,
# below one shift of evenness. A day off between shifts is charged per day
# only when the shifts carry no clock to measure a gap with.
SPACING_HOURS = 48
SPACING = 4
BACK_TO_BACK = 50
# The terms phase one of a solve settles before anything else is weighed.
COVERAGE = ("unfilled", "role", "manager")
# Hours are integers in the model: tenths of an hour (the weekly-hours rule);
# shifts and nights count ten to a unit likewise.
HOUR_SCALE = 10
SHIFT_SCALE = 10
NIGHT_SCALE = 10


class Term:
    def __init__(self, weight: int, expression, note: str = "", kind: str = ""):
        self.weight, self.expression, self.note, self.kind = weight, expression, note, kind


class Model:
    def __init__(self, problem):
        self.problem = problem
        self.cp = cp_model.CpModel()
        self.x: Dict[Tuple[str, int], cp_model.IntVar] = {
            key: self.cp.NewBoolVar("x_%d_%d" % (number, key[1]))
            for number, key in enumerate(sorted(problem.legal))
        }
        self.terms: List[Term] = []
        self._worked: Dict[Tuple[str, str], object] = {}
        self.by_slot: Dict[int, Dict[str, cp_model.IntVar]] = {}
        self.by_person: Dict[str, Dict[int, cp_model.IntVar]] = {}
        for (name, slot), var in self.x.items():
            self.by_slot.setdefault(slot, {})[name] = var
            self.by_person.setdefault(name, {})[slot] = var

    # -- variables ----------------------------------------------------------

    def placed(self, name: str, index: int):
        """The placement variable, or None when the pair is illegal."""
        return self.x.get((name, index))

    def on_slot(self, index: int, names=None) -> list:
        placed = self.by_slot.get(index, {})
        if names is None:
            return list(placed.values())
        return [placed[name] for name in names if name in placed]

    def of_person(self, name: str) -> Dict[int, cp_model.IntVar]:
        return self.by_person.get(name, {})

    def bool_or(self, variables: list, label: str):
        """A boolean that is 1 exactly when one of `variables` is."""
        flag = self.cp.NewBoolVar(label)
        if not variables:
            self.cp.Add(flag == 0)
            return flag
        self.cp.AddMaxEquality(flag, variables)
        return flag

    # -- rules and prices ---------------------------------------------------

    def at_most(self, variables: list, limit: float, scale: Optional[list] = None) -> None:
        """Hard: Σ variables ≤ limit, the limit clamped at zero."""
        if not variables:
            return
        weights = scale or [1] * len(variables)
        self.cp.Add(sum(w * v for w, v in zip(weights, variables)) <= max(0, int(limit)))

    def price_excess(self, variables: list, limit: float, weight: int, note: str,
                     kind: str = "", scale: Optional[list] = None) -> None:
        """Soft: pay `weight` per unit by which Σ variables exceeds `limit`."""
        if not variables:
            return
        weights = scale or [1] * len(variables)
        total = sum(w * v for w, v in zip(weights, variables))
        excess = self.cp.NewIntVar(0, sum(weights), "excess_%d" % len(self.terms))
        self.cp.Add(excess >= total - int(limit))
        self.terms.append(Term(weight, excess, note, kind))

    def price(self, weight: int, expression, note: str = "", kind: str = "") -> None:
        self.terms.append(Term(weight, expression, note, kind))

    def cost(self, kinds=None):
        """The priced terms as one expression, optionally only some kinds."""
        return sum(term.weight * term.expression for term in self.terms
                   if kinds is None or term.kind in kinds)

    def worked(self, name: str, day: str):
        """The flag that `name` works any slot on `day`, built once."""
        key = (name, day)
        if key not in self._worked:
            placed = [var for index, var in self.of_person(name).items()
                      if self.problem.slots[index]["slot_date"] == day]
            self._worked[key] = self.bool_or(placed, "worked") if placed else None
        return self._worked[key]
