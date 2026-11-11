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
from app.bl.solver.competence import apply_competence
from app.bl.solver.continuity import apply_continuity, matched as continuity_matched
from app.bl.solver.cpu_budget import BUDGET
from app.bl.solver.explain import coverage_notes
from app.bl.solver import wishes
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
_COLUMNS = ("begins", "ends", "hours", "night", "load", "past")
# The longest phase one, and with a board the held phase, may each take, as
# a share of the limit. The last phase takes whatever they left, and never
# less than its own floor.
_FIRST_SHARE = 0.3
_LAST_FLOOR = {False: 0.7, True: 0.4}


def solve(problem, time_limit: float = 10.0, workers: int = 8) -> dict:
    return answer(problem, *search(problem, time_limit, workers))


def search(problem, time_limit: float = 10.0, workers: int = 8) -> tuple:
    """Solve `problem`: the rows chosen (pins left out), the notes of what
    the answer still pays for, and the solve's metrics."""
    started = time.monotonic()
    model = Model(problem)
    apply_rules(model)
    apply_requests(model)
    apply_fairness(model)
    apply_competence(model)
    apply_stability(model)
    apply_continuity(model)
    # Threads are taken from the process's budget, so concurrent solves
    # queue instead of each getting a slice of the time it was promised.
    base = wishes.snapshot(model)
    with BUDGET.threads(max(1, int(workers))) as granted:
        solver, status, phases = _phases(model, max(0.2, float(time_limit)), granted)
        priced = wishes.price_of_wishes(model, base, solver, time_limit * wishes.SHARE, granted)
    chosen = [_row(problem, name, index) for (name, index), var in sorted(model.x.items())
              if solver.Value(var)]
    _shadow_reasons(problem, chosen)
    notes = [priced.get(note, note) for note in _notes(solver, model)]
    return chosen, notes, _metrics(problem, solver, status, started, phases)


def answer(problem, chosen: List[dict], notes: List[str], metrics: dict) -> dict:
    """What a build returns, from the rows chosen for `problem`: the audit's
    warnings, why a seat stayed empty, and what was kept. `chosen` may come
    from one solve or from several over parts of the grid (`chunks.py`)."""
    final = _ordered(problem, problem.pins + chosen)
    warnings = _warnings(problem, final)
    metrics.update(returned=len(final), accepted=len(final), warnings=len(warnings))
    metrics.update(continuity_matched(problem, chosen))
    notes = coverage_notes(problem, chosen) + notes
    if problem.kept_rows:
        metrics.update(absorbed(problem, chosen))
        notes.insert(0, absorbed_note(metrics))
    if problem.duty_load:
        notes.append(_duty_note(problem.duty_load))
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

    When phase one leaves seats empty, a gaps phase keeps its coverage and
    moves the empty seats to the end of the plan (`Model.gaps`), so a short
    team fills the schedule in order and stops where it runs out; the gaps
    it settles are a ceiling for every later phase too, so evenness never
    scatters them back across the week.

    A rebuild that keeps a board (D37) adds a phase between the two. Phase
    one keeps as much of the board as the best coverage allows; the middle
    phase holds those rows where they are and weighs everything else, so
    the change is filled in well around them; the last phase may then move
    a kept row, and its answer is taken only when it is strictly better than
    the held one. Without the middle phase the last one started from an
    arbitrary fill of the change, and within its time limit it often bought
    an improvement by moving people the best answer keeps in place: the same
    change moved some people on one build and none on the next.

    The last phase gets whatever the earlier ones left of the limit:
    coverage is usually proven in milliseconds, and a fixed split threw the
    rest of its share away. Returns the answer's solver and status, and what
    each phase did (`_phase`)."""
    coverage = model.cost(COVERAGE)
    kept = _kept(model)
    share = time_limit * _FIRST_SHARE
    first, found = _coverage_phase(model, coverage, kept, share, workers)
    phases = {"coverage": _phase(first, found, share)}
    model.cp.Add(coverage <= _value(first, coverage))
    gaps = sum(model.gaps)
    if model.gaps and _value(first, gaps):
        # Seats stay empty: move them to the end of the plan (`Model.gaps`).
        # A board's kept rows stay kept; only what moves anyway is reordered.
        if kept is not None:
            model.cp.Add(kept >= _value(first, kept))
        first, found = _gaps_phase(model, gaps, first, found, share / 2, workers)
        phases["gaps"] = _phase(first, found, share / 2)
        model.cp.Add(gaps <= _value(first, gaps))
    model.cp.Minimize(model.cost())
    _hint(model, first)
    start = (first, found)
    if kept is not None:
        held = _held_phase(model, first, share, workers)
        phases["held"] = _phase(*(held or (None, None)), share)
        start = held or start
        _hint(model, start[0])
    spent = sum(phase["wall_ms"] for phase in phases.values()) / 1000.0
    remaining = max(time_limit * _LAST_FLOOR[kept is not None], time_limit - spent)
    last = _solver(remaining, workers)
    status = last.Solve(model.cp)
    phases["balance"] = _phase(last, status, remaining)
    if status not in _STATUS:
        return start + (phases,)
    if kept is not None and start[0] is not first and \
            last.ObjectiveValue() >= start[0].ObjectiveValue():
        return start + (phases,)
    return last, status, phases


def _phase(solver, status, limit: float) -> dict:
    """What one phase did: its verdict, the time it was given and took, and
    how far its answer may be from the best (`gap` in the objective's units,
    `gap_pct` relative to the answer). A held phase that found nothing is
    `unknown`."""
    measured = {"status": "unknown", "limit_ms": int(limit * 1000), "wall_ms": 0}
    if solver is None:
        return measured
    measured.update(status=solver.StatusName(status).lower(),
                    wall_ms=int(solver.WallTime() * 1000),
                    conflicts=int(solver.NumConflicts()), branches=int(solver.NumBranches()))
    if status in _STATUS:
        measured.update(_gap(solver))
    return measured


def _gap(solver) -> dict:
    objective = int(round(solver.ObjectiveValue()))
    bound = int(round(solver.BestObjectiveBound()))
    gap = max(0, objective - bound)
    return {"objective": objective, "bound": bound, "gap": gap,
            "gap_pct": round(100.0 * gap / max(1, abs(objective)), 2)}


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


def _gaps_phase(model: Model, gaps, first, found, seconds: float, workers: int):
    """The seats that must stay empty, as late in the plan as they can be.
    Starts from phase one's answer and falls back to it if it finds nothing."""
    _hint(model, first)
    model.cp.Minimize(gaps)
    solver = _solver(seconds, workers)
    status = solver.Solve(model.cp)
    return (solver, status) if status in _STATUS else (first, found)


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


def _duty_note(load) -> str:
    """Why someone on מכלול duty got fewer shifts: the duty was counted."""
    people = ", ".join("%s (%d)" % (name, load[name]) for name in sorted(load))
    return "תורנויות המכלול נספרו בעומס, כל יום תורנות כמשמרת לפי משקלו: %s" % people


def _notes(solver, model: Model) -> List[str]:
    """Every priced term the answer still pays for, but coverage: an empty
    seat, role or shift manager is explained from the answer instead
    (`explain.coverage_notes`), with who could not take it and why."""
    notes = [term.note for term in model.terms
             if term.note and term.kind not in COVERAGE
             and _value(solver, term.expression) > 0]
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


def _metrics(problem, solver, status, started, phases) -> dict:
    return {
        "date": problem.dates[0] if problem.dates else "",
        "through": problem.dates[-1] if problem.dates else "",
        "status": "complete" if problem.slots else "skipped",
        "duration_ms": int((time.monotonic() - started) * 1000),
        "returned": 0, "accepted": 0, "rejected": 0, "repaired": False,
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        "engine": "solver",
        "solver_status": _STATUS[status],
        "objective": int(solver.ObjectiveValue()),
        "bound": _gap(solver)["bound"],
        "gap_pct": _gap(solver)["gap_pct"],
        "solver_ms": sum(phase["wall_ms"] for phase in phases.values()),
        "variables": len(problem.legal),
        "phases": phases,
    }
