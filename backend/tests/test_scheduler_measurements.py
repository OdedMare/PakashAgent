"""Input-aware planning and repeatable comparison without a live model."""

import json

import pytest

from app.bl.scheduler import build_slots, plan_spans
from app.bl.scheduler.compare import compare, main
from app.bl.scheduler.quality import no_worse, quality
from app.bl.audit import audit

MORNING = "בוקר"


def _week_profile():
    return {
        "workplace": {"name": "מוקד"},
        "employees": [{"name": "דנה"}, {"name": "יוסי"}, {"name": "רון"}],
        "shifts": [{"name": MORNING, "start_time": "07:00", "end_time": "15:00", "days": [],
                    "staffing": [{"days": [], "headcount": 1, "required_roles": []}]}],
    }


def assignment(day, employee="דנה", shift=MORNING):
    return dict(employee=employee, date=day, shift=shift, reason="זמין ומוסמך למשמרת")


def test_a_long_period_is_solved_in_four_week_blocks_without_dividing_a_day():
    spans = plan_spans(_week_profile(), "2026-10-01", "2026-11-30")
    assert [len(span["dates"]) for span in spans] == [28, 28, 5]
    assert spans[1]["date"] == "2026-10-29"


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
