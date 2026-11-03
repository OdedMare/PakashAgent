"""The solver benchmark keeps running: its scenarios build, solve and measure."""

from benchmarks.measure import measure
from benchmarks.scenarios import SCENARIOS
from benchmarks.solver_bench import COLUMNS, compare, run, table
from app.bl.solver.problem import slots_for


def test_every_scenario_builds_a_slot_grid():
    for build in SCENARIOS.values():
        scenario = build()
        assert slots_for(scenario.profile, scenario.starts_on, scenario.ends_on)


def test_the_small_scenario_is_measured_on_every_column():
    results = run(["small"], time_limit=1.0, workers=2, repeat=1)

    measured = results["small"]
    assert set(COLUMNS) <= set(measured)
    assert measured["unfilled_seats"] == 0
    assert measured["status"] in ("optimal", "feasible")
    assert set(measured["phases"]) == {"coverage", "balance"}
    assert "small" in table(results)


def test_compare_marks_direction_per_measure():
    before = {"x": {"unfilled_seats": 2, "prefers_met_pct": 50.0, "status": "feasible"}}
    after = {"x": {"unfilled_seats": 1, "prefers_met_pct": 40.0, "status": "optimal"}}

    lines = compare(before, after)

    assert any("unfilled_seats" in line and line.endswith("better") for line in lines)
    assert any("prefers_met_pct" in line and line.endswith("WORSE") for line in lines)
    assert not any("status" in line for line in lines)


def test_soft_inputs_are_counted_against_the_answer():
    scenario = SCENARIOS["small"]()
    soft = next(item for item in scenario.availability if item["is_hard"] is False)
    rows = [{"employee": soft["employee"], "shift": "בוקר", "date": soft["date"], "reason": "x"}]
    result = {"assignments": rows, "slots": [], "warnings": [], "metrics": {}}

    assert measure(scenario, result)["soft_absences_broken"] == 1
