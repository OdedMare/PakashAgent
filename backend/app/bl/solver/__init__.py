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
| `fairness.py` | Closers, even hours and nights, a day off between shifts |
| `solve.py` | Solving, reasons, notes, warnings and metrics |
| `rows.py` | Row and roster helpers |
"""

from typing import List, Optional

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
    time_limit: float = 10.0,
    workers: int = 8,
) -> dict:
    """Assign every slot from `starts_on` through `ends_on` in one solve.

    `required_assignments` are pins; rows of `already_scheduled` outside the
    span (or on shifts outside `shift_names`) stand as they are, and rows
    inside it are rebuilt. `history` is the time before the span: it counts
    for rest, runs of days and the load each person already carries.
    """
    slots = slots_for(profile, starts_on, ends_on, shift_names)
    if not slots:
        return _empty(starts_on, ends_on)
    problem = Problem(profile, slots, availability, history, required_assignments,
                      already_scheduled, requests)
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
