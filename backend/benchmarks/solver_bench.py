"""The solver benchmark: solve fixed synthetic teams and print what came out.

    cd backend
    python -m benchmarks.solver_bench                       # every scenario
    python -m benchmarks.solver_bench -s small -s nights -t 5
    python -m benchmarks.solver_bench --save before.json
    python -m benchmarks.solver_bench --compare before.json   # after a change

Every change to `app/bl/solver/` that is meant to make schedules better or
faster should be run through this before and after: the tests say a
schedule is legal, this says whether it got better. `--repeat` solves each
scenario several times and reports the median, since a multi-threaded solve
stopped by the clock is not the same answer twice.

No database, no model and no network: the scenarios are built in memory
(`scenarios.py`) and measured from the answer (`measure.py`).
"""

import argparse
import json
import sys
from statistics import median
from typing import Dict, List

from app.bl.solver import generate_span
from benchmarks.measure import measure
from benchmarks.scenarios import SCENARIOS

# Columns printed, in order; the rest is kept in the saved JSON.
COLUMNS = ("status", "unfilled_seats", "missing_roles", "warnings", "soft_absences_broken",
           "prefers_met_pct", "soft_avoids_broken", "shift_spread", "night_spread",
           "shifts_stddev", "short_rests", "min_rest_hours", "gap_pct", "wall_ms")
# Measures where a larger number is the better schedule.
HIGHER_IS_BETTER = ("prefers_met_pct", "min_rest_hours")


def run(names: List[str], time_limit: float, workers: int, repeat: int) -> Dict[str, dict]:
    results = {}
    for name in names:
        scenario = SCENARIOS[name]()
        runs = [measure(scenario, generate_span(
            scenario.profile, scenario.starts_on, scenario.ends_on,
            availability=scenario.availability, requests=scenario.requests,
            time_limit=time_limit, workers=workers)) for _ in range(max(1, repeat))]
        results[name] = _median(runs)
    return results


def _median(runs: List[dict]) -> dict:
    """The median of every number across runs; the rest from the first."""
    merged = dict(runs[0], runs=len(runs))
    for key, value in runs[0].items():
        values = [item[key] for item in runs]
        if isinstance(value, (int, float)) and not isinstance(value, bool) \
                and all(isinstance(item, (int, float)) for item in values):
            merged[key] = median(values)
    return merged


def compare(before: Dict[str, dict], after: Dict[str, dict]) -> List[str]:
    """One line per measure that moved, marked better or worse."""
    lines = []
    for name, current in after.items():
        previous = before.get(name)
        if not previous:
            continue
        for key in COLUMNS:
            old, new = previous.get(key), current.get(key)
            if old == new or not all(isinstance(v, (int, float)) for v in (old, new)):
                continue
            better = (new > old) == (key in HIGHER_IS_BETTER)
            lines.append("%-10s %-22s %10s -> %-10s %s" % (
                name, key, old, new, "better" if better else "WORSE"))
    return lines


def table(results: Dict[str, dict]) -> str:
    header = ["scenario"] + list(COLUMNS)
    rows = [[name] + ["" if result.get(key) is None else str(result.get(key)) for key in COLUMNS]
            for name, result in results.items()]
    widths = [max(len(row[column]) for row in [header] + rows) for column in range(len(header))]
    return "\n".join("  ".join(cell.ljust(width) for cell, width in zip(row, widths))
                     for row in [header] + rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("-s", "--scenario", action="append", choices=sorted(SCENARIOS),
                        help="run only this scenario (repeatable); default every one")
    parser.add_argument("-t", "--time-limit", type=float, default=10.0,
                        help="seconds per solve, as solver_time_limit_seconds (default 10)")
    parser.add_argument("-w", "--workers", type=int, default=8, help="solver threads (default 8)")
    parser.add_argument("-r", "--repeat", type=int, default=1, help="solves per scenario (median)")
    parser.add_argument("--save", help="write the results to this JSON file")
    parser.add_argument("--compare", help="a JSON file saved earlier to compare against")
    args = parser.parse_args(argv)

    results = run(args.scenario or list(SCENARIOS), args.time_limit, args.workers, args.repeat)
    print(table(results))
    if args.save:
        with open(args.save, "w", encoding="utf-8") as handle:
            json.dump({"time_limit": args.time_limit, "workers": args.workers,
                       "results": results}, handle, ensure_ascii=False, indent=1)
    if args.compare:
        with open(args.compare, encoding="utf-8") as handle:
            before = json.load(handle)["results"]
        print("\n" + ("\n".join(compare(before, results)) or "no measure moved"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
