"""Solving the model and reading the answer back as assignments.

Every placed row carries the reason it was placed (D8), written from what
the solver was asked to weigh: the closure cycle, a met preference, the
shift manager's seat, a required role, or availability and load. Every
priced term the solution still pays for that carries a note — an unfilled
seat, a soft wish code had to break — becomes one line of `notes`.
"""

import time
from typing import List

from ortools.sat.python import cp_model

from app.bl.audit import audit
from app.bl.schedule_requests import covers
from app.bl.solver.cpu_budget import BUDGET
from app.bl.solver.fairness import apply_fairness
from app.bl.solver.model import COVERAGE, Model
from app.bl.solver.requests import apply_requests
from app.bl.solver.rows import roles
from app.bl.solver.rules import apply_rules
from app.bl.solver.stability import absorbed, absorbed_note, apply_stability, kept_reason
from app.bl import rotation
from app.common.errors import AgentError

SUMMARY = "השיבוץ נבנה בפותר אילוצים לפי זמינות, כשירות, כללים, בקשות והוגנות."
_STATUS = {cp_model.OPTIMAL: "optimal", cp_model.FEASIBLE: "feasible"}
_COLUMNS = ("begins", "ends", "hours", "night", "past")


def solve(problem, time_limit: float = 10.0, workers: int = 8) -> dict:
    started = time.monotonic()
    model = Model(problem)
    apply_rules(model)
    apply_requests(model)
    apply_fairness(model)
    apply_stability(model)
    # Threads are taken from the process's budget, so concurrent solves
    # queue instead of each getting a slice of the time it was promised.
    with BUDGET.threads(max(1, int(workers))) as granted:
        solver, status = _phases(model, max(0.2, float(time_limit)), granted)
    chosen = [_row(problem, name, index) for (name, index), var in sorted(model.x.items())
              if solver.Value(var)]
    _shadow_reasons(problem, chosen)
    final = _ordered(problem, problem.pins + chosen)
    warnings = _warnings(problem, final)
    metrics = _metrics(problem, solver, status, started, final)
    metrics["warnings"] = len(warnings)
    notes = _notes(solver, model)
    if problem.kept_rows:
        metrics.update(absorbed(problem, chosen))
        notes.insert(0, absorbed_note(metrics))
    return {
        "slots": problem.slots, "assignments": final, "notes": notes,
        "warnings": warnings, "summary": SUMMARY, "metrics": metrics,
    }


def _phases(model: Model, time_limit: float, workers: int):
    """Coverage first, then everything else without giving any of it back.

    Phase one prices only unfilled seats, missing roles and the shift
    manager; its answer becomes a hint and its coverage a ceiling for the
    last phase, which weighs wishes and fairness. Lexicographic in fact, not
    only in the weights, so a hard week never trades a seat for evenness.

    A rebuild that keeps a board (D37) adds a phase between the two. Phase
    one keeps as much of the board as the best coverage allows; the middle
    phase holds those rows where they are and weighs everything else, so
    the change is filled in well around them; the last phase may then move
    a kept row, and its answer is taken only when it is strictly better than
    the held one. Without the middle phase the last one started from an
    arbitrary fill of the change, and within its time limit it often bought
    an improvement by moving people the best answer keeps in place: the same
    change moved some people on one build and none on the next."""
    coverage = model.cost(COVERAGE)
    kept = _kept(model)
    first, found = _coverage_phase(model, coverage, kept, time_limit * 0.3, workers)
    model.cp.Add(coverage <= _value(first, coverage))
    model.cp.Minimize(model.cost())
    _hint(model, first)
    start = (first, found)
    if kept is not None:
        start = _held_phase(model, first, time_limit * 0.3, workers) or start
        _hint(model, start[0])
    last = _solver(time_limit * (0.4 if kept is not None else 0.7), workers)
    status = last.Solve(model.cp)
    if status not in _STATUS:
        return start
    if kept is not None and start[0] is not first and \
            last.ObjectiveValue() >= start[0].ObjectiveValue():
        return start
    return last, status


def _coverage_phase(model: Model, coverage, kept, seconds: float, workers: int):
    """Phase one: the best coverage; with a board, then the most rows kept."""
    if kept is None:
        model.cp.Minimize(coverage)
    else:
        for key, var in model.x.items():
            model.cp.AddHint(var, key in model.problem.keep)
        # One unit of coverage outweighs every kept row.
        model.cp.Minimize(coverage * (len(model.problem.keep) + 1) - kept)
    solver = _solver(seconds, workers)
    found = solver.Solve(model.cp)
    if found not in _STATUS:
        raise AgentError("פותר האילוצים לא הצליח לבנות סידור (%s)" % solver.StatusName(found))
    return solver, found


def _held_phase(model: Model, first, seconds: float, workers: int):
    """The full objective with every kept row phase one kept held in place.

    Solved on a copy, so the hold binds this phase only. None when it finds
    nothing, and the last phase starts from phase one instead."""
    held = model.cp.Clone()
    for key, var in model.x.items():
        if key in model.problem.keep and first.Value(var):
            held.Add(held.GetBoolVarFromProtoIndex(var.Index()) == 1)
    solver = _solver(seconds, workers)
    status = solver.Solve(held)
    return (solver, status) if status in _STATUS else None


def _hint(model: Model, solver) -> None:
    model.cp.ClearHints()
    for var in model.x.values():
        model.cp.AddHint(var, solver.Value(var))


def _kept(model: Model):
    """How many of the board's rows stand where they were; None without a board."""
    variables = [model.x[key] for key in sorted(model.problem.keep) if key in model.x]
    return sum(variables) if variables else None


def _solver(seconds: float, workers: int):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = 0
    return solver


def _row(problem, name: str, index: int) -> dict:
    slot = problem.slots[index]
    row = {"employee": name, "shift": slot["shift_name"], "date": slot["slot_date"]}
    row["reason"] = _reason(problem, name, index, row)
    return row


def _reason(problem, name: str, index: int, row: dict) -> str:
    person, slot = problem.people[name], problem.slots[index]
    if (name, index) in problem.keep:
        return kept_reason(problem, name, index)
    if person.get("rotation_group") and problem.closes(name, index):
        return "%s סוגר/ת במועד הזה; השיבוץ עומד במחזור המחייב." % (
            rotation.label(rotation.exit_pattern(problem.profile, person),
                           person.get("rotation_group"), problem.profile) or "קבוצת הסגירה")
    wished = [request["reason"] for request in problem.requests
              if request["kind"] == "prefer" and name in request["employees"]
              and covers(request, row["shift"], row["date"])]
    if wished:
        return "שובץ/ה לפי בקשה: %s." % wished[0]
    if slot.get("requires_shift_manager") and person.get("is_shift_manager"):
        return "שובץ/ה כמפקד/ת המשמרת, לפי זמינות ואיזון עומס."
    matched = sorted(set(slot.get("required_roles") or []).intersection(roles(person)))
    if matched:
        return "שובץ/ה לתפקיד %s, לפי זמינות ואיזון עומס." % ", ".join(matched)
    return "שובץ/ה לפי זמינות, כשירות ואיזון עומס."


def _shadow_reasons(problem, chosen: List[dict]) -> None:
    """A placed נחפף/ת's row names who they shadow on it."""
    for row in chosen:
        if row["employee"] not in problem.shadows:
            continue
        beside = [other["employee"] for other in chosen + problem.fixed
                  if other["shift"] == row["shift"] and other["date"] == row["date"]
                  and other["employee"] in problem.trainers_of(row["employee"])]
        row["reason"] = "שובץ/ה בחפיפה לצד %s; לא נספר/ת בתקן המשמרת." % (
            ", ".join(dict.fromkeys(beside)) or "חונך/ת")


def _ordered(problem, rows: List[dict]) -> List[dict]:
    order = {name: position for position, name in enumerate(problem.people)}
    slots = {(slot["shift_name"], slot["slot_date"]): index for index, slot in enumerate(problem.slots)}
    return sorted(rows, key=lambda row: (
        row["date"], slots.get((row["shift"], row["date"]), 0), order.get(row["employee"], 0)))


def _notes(solver, model: Model) -> List[str]:
    notes = [term.note for term in model.terms
             if term.note and _value(solver, term.expression) > 0]
    return list(dict.fromkeys(notes))


def _value(solver, expression) -> int:
    if isinstance(expression, int):
        return expression
    return int(solver.Value(expression))


def _warnings(problem, final: List[dict]) -> List[dict]:
    pinned = {(row["employee"], row["shift"], row["date"]) for row in problem.pins}
    context = [{key: value for key, value in row.items() if key not in _COLUMNS}
               for row in problem.fixed if (row["employee"], row["shift"], row["date"]) not in pinned]
    dates = set(problem.dates)
    return [
        item for item in audit(context + final, list(problem.shifts.values()), problem.employees,
                               problem.availability, problem.profile, problem.slots)
        if item.get("date") in dates or not item.get("date")
    ]


def _metrics(problem, solver, status, started, final) -> dict:
    return {
        "date": problem.dates[0] if problem.dates else "",
        "through": problem.dates[-1] if problem.dates else "",
        "status": "complete" if problem.slots else "skipped",
        "duration_ms": int((time.monotonic() - started) * 1000),
        "returned": len(final), "accepted": len(final), "rejected": 0,
        "repaired": False,
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        "engine": "solver",
        "solver_status": _STATUS[status],
        "objective": int(solver.ObjectiveValue()),
        "variables": len(problem.legal),
    }
