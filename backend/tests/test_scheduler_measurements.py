"""Input-aware planning and repeatable comparison without a live model."""

import json

import pytest

from app.bl.scheduler import MODE_WEEK, build_slots, plan_spans
from app.bl.scheduler import planning
from app.bl.scheduler.compare import compare, main
from app.bl.scheduler.quality import no_worse, quality
from app.bl.audit import audit
from tests.test_scheduler import _week_profile
from tests.test_scheduler_recovery import assignment


def test_candidate_pressure_splits_below_the_staffing_limit_without_dividing_a_day(monkeypatch):
    profile = _week_profile()
    profile["employees"] = [{"name": "אדם %d" % index, "notes": "מידע חשוב " * 20}
                            for index in range(60)]
    slots = build_slots(profile, "2026-10-05", "2026-10-11")
    one = planning.input_chars(profile, slots[:1], [])
    full = planning.input_chars(profile, slots, [])
    monkeypatch.setattr(planning, "MAX_SPAN_INPUT_CHARS", one + (full - one) // 3)
    spans = plan_spans(profile, "2026-10-05", "2026-10-11", MODE_WEEK)
    assert len(spans) > 1
    assert [day for span in spans for day in span["dates"]] == [slot["slot_date"] for slot in slots]
    for span in spans:
        scoped = [slot for slot in slots if slot["slot_date"] in span["dates"]]
        assert planning.input_chars(profile, scoped, []) <= planning.MAX_SPAN_INPUT_CHARS


def test_recorded_constraint_pressure_changes_planning_without_dropping_rules(monkeypatch):
    profile = _week_profile()
    profile["rules"] = [{"text": "הנחיה שהמנהל ניסח", "priority": "hard"}]
    slots = build_slots(profile, "2026-10-05", "2026-10-11")
    monkeypatch.setattr(planning, "MAX_SPAN_INPUT_CHARS", planning.input_chars(profile, slots, []) + 100)
    assert len(plan_spans(profile, "2026-10-05", "2026-10-11", MODE_WEEK)) == 1
    rows = [dict(employee="דנה", date=slot["slot_date"], available=False,
                 is_hard=False, reason="העדפה שהמנהל ניסח " * 60) for slot in slots]
    constrained = plan_spans(profile, "2026-10-05", "2026-10-11", MODE_WEEK, rows)
    assert len(constrained) > 1
    assert sum(len(span["dates"]) for span in constrained) == 7


def test_an_oversized_single_day_is_not_truncated_or_split(monkeypatch):
    monkeypatch.setattr(planning, "MAX_SPAN_INPUT_CHARS", 1)
    spans = plan_spans(_week_profile(), "2026-10-05", "2026-10-06", MODE_WEEK)
    assert [span["dates"] for span in spans] == [["2026-10-05"], ["2026-10-06"]]


def test_quality_uses_existing_coverage_and_counts_shadow_trainees_correctly():
    profile = _week_profile()
    profile["employees"][0].update(is_trainee=True, counts_toward_staffing=False)
    slots = build_slots(profile, "2026-10-06", "2026-10-06")
    roster = [assignment("2026-10-06")]
    warnings = audit(roster, profile["shifts"], profile["employees"], slots=slots, profile=profile)
    measured = quality(roster, slots, profile, warnings)
    assert measured["coverage"]["assigned"] == 0
    assert measured["unfilled_seats"] == 1
    assert len(measured["by_employee"]) == 3  # Zeros belong in the distribution too.


def test_quality_comparison_detects_a_worsened_existing_hours_violation():
    before = [dict(code="over_hours", severity="warning", employee="דנה",
                   details=dict(hours=48, limit=45, year=2026, week=41))]
    after = [dict(before[0], details=dict(hours=56, limit=45, year=2026, week=41))]
    assert not no_worse(before, after)
    assert no_worse(after, before)


def snapshot():
    return dict(profile=_week_profile(), starts_on="2026-10-05", ends_on="2026-10-06",
                baseline=dict(assignments=[assignment("2026-10-05")],
                              metrics=dict(model_calls=3, failed_calls=1, prompt_chars=4000)),
                candidate=dict(assignments=[assignment("2026-10-05"), assignment("2026-10-06", "יוסי")],
                               metrics=[dict(model_calls=1, prompt_chars=1200),
                                        dict(model_calls=1, prompt_chars=1000)]))


def test_saved_comparison_reaudits_both_results_and_separates_speed_from_quality():
    result = compare(snapshot())
    assert result["checks_not_worse"]
    assert result["baseline"]["quality"]["unfilled_seats"] == 1
    assert result["candidate"]["quality"]["unfilled_seats"] == 0
    assert result["delta"]["model_calls"] == -1
    assert result["delta"]["prompt_chars"] == -1800
    assert "hours_stddev" in result["delta"]


def test_comparison_command_reads_snapshots_and_writes_json(tmp_path, monkeypatch):
    source, output = tmp_path / "snapshot.json", tmp_path / "comparison.json"
    source.write_text(json.dumps(snapshot(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["compare", str(source), "--output", str(output)])
    main()
    assert json.loads(output.read_text())["delta"]["model_calls"] == -1


def test_comparison_refuses_results_outside_the_shared_period():
    data = snapshot()
    data["candidate"]["assignments"].append(assignment("2026-10-07"))
    with pytest.raises(ValueError, match="shared comparison period"):
        compare(data)
