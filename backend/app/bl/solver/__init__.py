"""Assigning people into the slot grid with a constraint solver (D34).

OR-Tools CP-SAT solves a whole span at once: one boolean per legal
(person, slot) pair, the workplace's rules and every hard request as
constraints, and one objective pricing unfilled seats, missing roles,
soft wishes and an uneven share. It replaces the day-by-day greedy filler
and the model-driven scheduler: the language model now only translates
the manager's words into structured requests (`bl/directive_agent/`), and
the arithmetic of who goes where is never generated. Every answer is as
good as the solver could prove in its time limit; among equally good
schedules the pick may differ from one build to the next.

| Module | Owns |
|---|---|
| `problem.py` | `Problem`: slots, roster, fixed rows and which placements are legal |
| `model.py` | `Model`: the CP-SAT model, its variables and priced terms; the weights |
| `rules.py` | Seats, roles, the shift manager, נחפפים beside a trainer, rest, runs of days, weekly hours |
| `requests.py` | Structured requests (`bl/schedule_requests.py`) and soft availability |
| `fairness.py` | Closers, shifts and nights spread to per-person targets, the longest rest between shifts |
| `ledger.py` | The fairness ledger: load carried in the eight weeks before the fixed rows (D51) |
| `continuity.py` | A new week keeps the shape of the last two, among otherwise equal schedules (D53) |
| `competence.py` | A reservist's days a week (cap, minimum, one block); shifts balanced by competence so the weakest are not staffed together |
| `stability.py` | Absorbing a change into an existing board: moving as few rows as it needs |
| `solve.py` | Solving, reasons, notes, warnings and metrics |
| `chunks.py` | A large team solved in chunks of shifts, alphabetically, each seeing the last |
| `explain.py` | Why an empty seat, role or shift manager stayed empty: who could not take it, and why |
| `wishes.py` | What honouring a broken soft wish would have cost: a short re-solve with it binding |
| `cpu_budget.py` | How many solver threads the process runs at once; a solve waits for its share |
| `rows.py` | Row and roster helpers |
"""

from typing import List, Optional

from app.bl.solver import chunks
from app.bl.solver.problem import Problem, checked_requests, slots_for
from app.bl.solver.solve import SUMMARY, solve


def generate_span(
    profile: dict,
    starts_on: str,
    ends_on: str,
    availability: Optional[List[dict]] = None,
    history: Optional[List[dict]] = None,
    required_assignments: Optional[List[dict]] = None,
    already_scheduled: Optional[List[dict]] = None,
    requests: Optional[List[dict]] = None,
    shift_names: Optional[List[str]] = None,
    keep: Optional[List[dict]] = None,
    duties: Optional[List[dict]] = None,
    time_limit: float = 10.0,
    workers: int = 8,
    chunk_people: int = chunks.MIN_PEOPLE,
    chunk_shifts: int = chunks.SHIFTS,
) -> dict:
    """Assign every slot from `starts_on` through `ends_on`: in one solve,
    or for a roster of `chunk_people` or more in chunks of `chunk_shifts`
    shift types, alphabetically (`chunks.py`; zero for either turns it off).

    `required_assignments` are pins; rows of `already_scheduled` outside the
    span (or on shifts outside `shift_names`) stand as they are, and rows
    inside it are rebuilt. `history` is the time before the span: it counts
    for rest, runs of days and the load each person already carries.
    `keep` is the board as it stood on these dates: each row is rewarded for
    staying where it is (`stability.py`), so a new person or a new shift is
    absorbed with as few moves as evenness and coverage call for.
    `duties` are the team's מכלול duties around the span: each day counts
    as its weight in shifts already carried (`problem._duty_load`). What
    blocks a day comes through `availability`, not here.
    """
    slots = slots_for(profile, starts_on, ends_on, shift_names)
    if not slots:
        return _empty(starts_on, ends_on)
    inputs = dict(availability=availability, history=history,
                  required_assignments=required_assignments,
                  already_scheduled=already_scheduled, requests=requests, keep=keep,
                  duties=duties)
    problem = Problem(profile, slots, **inputs)
    groups = chunks.plan(problem, chunk_people, chunk_shifts)
    if groups:
        return chunks.solve_chunks(problem, groups, inputs, time_limit, workers)
    return solve(problem, time_limit, workers)


def generate_day(profile: dict, day: str, **options) -> dict:
    """One date: `generate_span` over a single day."""
    return generate_span(profile, day, day, **options)


def _empty(starts_on: str, ends_on: str) -> dict:
    return {
        "slots": [], "assignments": [], "notes": [], "warnings": [], "summary": SUMMARY,
        "metrics": {"date": starts_on, "through": ends_on, "status": "skipped",
                    "accepted": 0, "warnings": 0, "engine": "solver", "total_tokens": 0},
    }


__all__ = ["checked_requests", "generate_day", "generate_span"]
