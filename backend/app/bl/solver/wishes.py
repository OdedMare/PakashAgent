"""What honouring a broken soft wish would have cost.

"שובץ/ה למרות בקשה רכה" tells the manager a wish was broken but not why,
and the honest answer is always a trade: a seat, another wish, evenness,
rest. So after the answer is found, each broken wish (the costliest first,
at most `PROBES` of them) is solved again with that wish made binding,
for a short share of the time limit on top of it, and the difference is
written beside it:

- a seat the binding wish would leave empty — claimed only when keeping
  today's coverage beside the wish is proven impossible, and the seat named
  from a second solve that may give coverage away;
- "cannot be honoured" when the hard rules forbid it outright;
- "no extra cost" when the probe did as well or better — the time limit,
  not a trade, is then what broke it;
- otherwise, marked as a quick check, the other soft wishes it would
  break, or the largest prices it would raise — evenness of shifts or
  nights, rest between shifts, the closure cycle, competence, the board
  kept in place.

A probe cut short by the clock before it answers adds nothing.

The probes solve copies taken before any phase added its coverage
ceiling, and set their own. Nothing here changes the answer; it only
explains it.
"""

from typing import Dict, List

from ortools.sat.python import cp_model

from app.bl.audit import counts_toward_staffing
from app.bl.solver.model import COVERAGE, Model

# Broken wishes probed per solve, the costliest first.
PROBES = 3
# Share of the time limit all probes together may take, on top of it.
SHARE = 0.3
_FOUND = (cp_model.OPTIMAL, cp_model.FEASIBLE)
_PRICE = {
    "shifts": "היה פוגע באיזון מספר המשמרות בין העובדים",
    "nights": "היה פוגע באיזון הלילות בין העובדים",
    "spacing": "היה מקצר את המנוחה בין משמרות",
    "closer": "היה מוציא סוגר/ת מהסגירה שלו/ה",
    "competence": "היה פוגע באיזון הרמה המקצועית במשמרות",
    "keep": "היה מזיז שיבוצים מהסידור הקיים",
    "balance": "היה פוגע בבקשת איזון",
    "prefer": "היה מוותר על העדפה של עובד/ת",
    "shadow": "היה מצמצם משמרות חפיפה",
}


def snapshot(model: Model):
    """The model with its full objective, before any phase narrows it; None
    when there is no soft wish to probe."""
    if not any(term.kind == "wish" and term.note for term in model.terms):
        return None
    model.cp.Minimize(model.cost())
    return model.cp.Clone()


def price_of_wishes(model: Model, base, answer, seconds: float, workers: int) -> Dict[str, str]:
    """{broken wish's note: the note with what honouring it would cost}."""
    broken = _broken(model, answer)
    if base is None or not broken or seconds <= 0:
        return {}
    picked = broken[:PROBES]
    each = seconds / len(picked)
    explained = {}
    for note, terms in picked:
        cost = _probe(model, base, answer, note, terms, each, workers)
        if cost:
            explained[note] = "%s %s" % (note, cost)
    return explained


def _broken(model: Model, answer) -> List[tuple]:
    groups: Dict[str, list] = {}
    for term in model.terms:
        if term.kind == "wish" and term.note and hasattr(term.expression, "Index") \
                and answer.Value(term.expression) > 0:
            groups.setdefault(term.note, []).append(term)
    paid = lambda terms: sum(term.weight * answer.Value(term.expression) for term in terms)
    return sorted(groups.items(), key=lambda item: -paid(item[1]))


def _probe(model: Model, base, answer, note: str, terms: list, seconds: float, workers: int) -> str:
    """Solve again with this wish binding, in three short steps.

    First, is there any schedule with the wish kept and today's coverage
    kept? (No objective: it answers in a fraction of the time.) If that is
    proven impossible, the wish costs a seat, and a coverage-only solve
    names one. If one exists, it is the hint for a solve of the full
    objective, whose answer says what else gives. A step cut short by the
    clock claims nothing."""
    coverage = model.cost(COVERAGE)
    held = _binding(model, base, answer, terms)
    held.Add(coverage <= _cost(model, answer, COVERAGE))
    held.ClearObjective()
    found, status = _solve(held, seconds * 0.4, workers)
    if status == cp_model.INFEASIBLE:
        return _seat_lost(model, base, answer, terms, seconds * 0.4, workers)
    if status not in _FOUND:
        return ""
    priced = _binding(model, base, found, terms)
    priced.Add(coverage <= _cost(model, answer, COVERAGE))
    solver, status = _solve(priced, seconds * 0.6, workers)
    return _trade(model, answer, solver, note) if status in _FOUND else ""


def _seat_lost(model: Model, base, answer, terms: list, seconds: float, workers: int) -> str:
    free = _binding(model, base, answer, terms)
    free.Minimize(model.cost(COVERAGE))
    solver, status = _solve(free, seconds, workers)
    if status == cp_model.INFEASIBLE:
        return "לא ניתן לכבד אותה לצד הכללים המחייבים."
    empty = _emptied(model, answer, solver) if status in _FOUND else []
    if empty:
        more = " ועוד %d" % (len(empty) - 1) if len(empty) > 1 else ""
        return "כיבודה היה משאיר בחוסר את %s%s." % (empty[0], more)
    return "כיבודה היה משאיר משמרת בחוסר או בלי תפקיד נדרש."


def _binding(model: Model, base, hint, terms: list):
    """A copy of the model with these terms held at zero, hinted from
    `hint`'s placements (a placement the wish forbids hinted off)."""
    probe = base.Clone()
    forbidden = set()
    for term in terms:
        probe.Add(probe.GetIntVarFromProtoIndex(term.expression.Index()) == 0)
        forbidden.add(term.expression.Index())
    for var in model.x.values():
        probe.AddHint(probe.GetBoolVarFromProtoIndex(var.Index()),
                      0 if var.Index() in forbidden else hint.Value(var))
    return probe


def _solve(probe, seconds: float, workers: int):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.05, seconds)
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = 0
    return solver, solver.Solve(probe)


def _trade(model: Model, answer, probe, note: str) -> str:
    """With coverage kept: the other wishes it breaks, or the prices it raises."""
    others = [term.note for term in model.terms if term.kind == "wish" and term.note
              and term.note != note and probe.Value(term.expression) > 0
              and answer.Value(term.expression) == 0]
    others = list(dict.fromkeys(others))
    if _cost(model, probe) <= _cost(model, answer):
        return "ניתן היה לכבד אותה בלי מחיר נוסף; ייתכן שזמן הפתרון לא הספיק."
    if len(others) > 1:
        return "בבדיקה מהירה, כיבודה היה שובר %d בקשות רכות אחרות, למשל: %s" % (len(others), others[0])
    if others:
        return "בבדיקה מהירה, כיבודה היה שובר בקשה רכה אחרת: %s" % others[0]
    raised = sorted(((_cost(model, probe, (kind,)) - _cost(model, answer, (kind,)), kind)
                     for kind in _PRICE), reverse=True)
    reasons = [_PRICE[kind] for rise, kind in raised[:2] if rise > 0]
    return "בבדיקה מהירה, כיבודה %s." % " ו".join(reasons) if reasons else ""


def _emptied(model: Model, answer, probe) -> List[str]:
    """Slots the probe leaves with fewer counted people than the answer, and short."""
    problem, emptied = model.problem, []
    for index, slot in enumerate(problem.slots):
        placed = model.on_slot(index, problem.staff)
        if not placed:
            continue
        fixed = sum(counts_toward_staffing(problem.people.get(row["employee"]), problem.profile)
                    for row in problem.fixed_on(index))
        need = int(slot.get("headcount") or 0) - fixed
        before, after = (sum(solver.Value(var) for var in placed) for solver in (answer, probe))
        if after < before and after < need:
            emptied.append("%s בתאריך %s" % (slot["shift_name"], slot["slot_date"]))
    return emptied


def _cost(model: Model, solver, kinds=None) -> int:
    return sum(term.weight * _value(solver, term.expression) for term in model.terms
               if kinds is None or term.kind in kinds)


def _value(solver, expression) -> int:
    return expression if isinstance(expression, int) else int(solver.Value(expression))
