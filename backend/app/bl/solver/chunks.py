"""A large team is solved in chunks of shifts rather than all at once.

Every shift of forty people over four weeks in one model is thousands of
placement variables tied together by rest, evenness and the wishes, and the
time limit ends long before the solver has weighed them. So from
`MIN_PEOPLE` people up the grid is split by shift type: the shift names in
alphabetical order, `SHIFTS` to a chunk, and each chunk is solved on its
own, in that order.

A chunk is an ordinary solve over its own slots (`solve.search`). What the
earlier chunks placed stands for it as fixed rows, exactly as the rest of a
draft does: it counts for rest, runs of days, the weekly hours, a request's
limit and the load each person already carries, so the last chunk evens
out what the first ones handed out. Pins on a later chunk's shifts stand
from the first chunk on. The time limit is shared among the chunks by the
number of placements each has to decide, so a chunked build takes what a
whole one does.

The chunks are answered as one build (`solve.answer` over the whole grid):
one audit, one set of coverage notes, one count of what a rebuild kept.

A shift type left alone at the end joins the chunk before it, so no chunk
is a single shift; a grid of fewer than two chunks is solved whole.
"""

import time
from typing import Dict, List

from app.bl.solver.problem import Problem
from app.bl.solver.rows import assignment
from app.bl.solver.solve import answer, search

# From how many people on the roster a build is chunked, and how many shift
# types one chunk holds. Zero for either solves every build whole.
MIN_PEOPLE = 30
SHIFTS = 2


def plan(problem: Problem, min_people: int = MIN_PEOPLE, size: int = SHIFTS) -> List[List[str]]:
    """The chunks of this grid, each a list of shift names; [] when the
    build is to be solved whole."""
    if min_people <= 0 or size <= 0 or len(problem.people) < min_people:
        return []
    names = sorted({slot["shift_name"] for slot in problem.slots})
    groups = [names[start:start + size] for start in range(0, len(names), size)]
    if len(groups) > 1 and len(groups[-1]) < min(size, 2):
        groups[-2].extend(groups.pop())
    return groups if len(groups) > 1 else []


def solve_chunks(problem: Problem, groups: List[List[str]], inputs: dict,
                 time_limit: float = 10.0, workers: int = 8) -> dict:
    """Solve `problem` one group of shifts at a time and answer as one build.

    `inputs` are the arguments `problem` was built from besides its profile
    and slots (`availability`, `history`, `required_assignments`,
    `already_scheduled`, `requests`, `keep`, `duties`)."""
    started = time.monotonic()
    # Draft rows inside the grid are what is being rebuilt; a chunk must not
    # read the ones on another chunk's shifts as standing.
    standing = [row for row in map(assignment, inputs.get("already_scheduled") or [])
                if row and (row["shift"], row["date"]) not in problem.keys] + list(problem.pins)
    decided = {tuple(group): sum(1 for _, index in problem.legal
                                 if problem.slots[index]["shift_name"] in group)
               for group in groups}
    total = max(1, sum(decided.values()))
    chosen, notes, measured = [], [], []
    for group in groups:
        slots = [slot for slot in problem.slots if slot["shift_name"] in group]
        part = Problem(problem.profile, slots, **dict(inputs, already_scheduled=standing + chosen))
        rows, said, metrics = search(part, time_limit * decided[tuple(group)] / total, workers)
        chosen.extend(rows)
        notes.extend(note for note in said if note not in notes)
        measured.append(dict(metrics, shifts=list(group)))
    return answer(problem, chosen, notes, _metrics(measured, started))


def _metrics(measured: List[dict], started: float) -> dict:
    """The chunks' metrics as one build's: times, sizes and objectives
    added up, `optimal` only when every chunk was proven so, and each
    chunk's own numbers under `chunks`. `phases` adds up each phase's time
    across the chunks that ran it."""
    merged = dict(measured[0], through=measured[-1]["through"])
    for key in ("objective", "bound", "solver_ms", "variables"):
        merged[key] = sum(item[key] for item in measured)
    gap = max(0, merged["objective"] - merged["bound"])
    merged["gap_pct"] = round(100.0 * gap / max(1, abs(merged["objective"])), 2)
    merged["solver_status"] = "optimal" if all(
        item["solver_status"] == "optimal" for item in measured) else "feasible"
    merged["duration_ms"] = int((time.monotonic() - started) * 1000)
    merged["phases"] = _phases(measured)
    merged["chunks"] = [
        {key: item[key] for key in ("shifts", "solver_status", "objective", "bound", "gap_pct",
                                    "solver_ms", "variables", "phases")}
        for item in measured]
    merged.pop("shifts", None)
    return merged


def _phases(measured: List[dict]) -> Dict[str, dict]:
    phases: Dict[str, dict] = {}
    for item in measured:
        for name, phase in item["phases"].items():
            total = phases.setdefault(name, {"status": phase["status"], "limit_ms": 0, "wall_ms": 0})
            if phase["status"] != "optimal":
                total["status"] = phase["status"]
            for key in ("limit_ms", "wall_ms", "conflicts", "branches"):
                if key in phase:
                    total[key] = total.get(key, 0) + phase[key]
    return phases
