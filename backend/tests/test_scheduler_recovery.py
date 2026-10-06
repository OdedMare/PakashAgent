"""Draft retention, focused repair and bounded capacity recovery."""

import json

import pytest

from app.bl.scheduler import Scheduler
from app.common.errors.errors import AgentError, ModelOutputError
from tests.test_scheduler import MORNING, PROFILE, _reply, _week_profile


class Model:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []

    def complete_json(self, system, user, **kwargs):
        payload = json.loads(user)
        self.calls.append(payload)
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return answer(payload) if callable(answer) else answer


def assignment(day, employee="דנה", shift=MORNING):
    return dict(employee=employee, date=day, shift=shift, reason="זמין ומוסמך למשמרת")


def cover(payload):
    return _reply([assignment(slot["date"], "דנה" if int(slot["date"][-2:]) % 2 else "יוסי",
                              slot["shift"]) for slot in payload["period"]["slots"]])


@pytest.mark.parametrize("error", [AgentError("חיבור נקטע"), ModelOutputError("תשובה לא תקינה")])
def test_failed_repair_preserves_audited_draft_pins_and_warnings(error):
    profile = dict(PROFILE, shifts=[dict(PROFILE["shifts"][0], staffing=[{
        "days": [], "headcount": 2,
    }])])
    model = Model([_reply([]), error])
    result = Scheduler(model).generate_day(profile, "2026-10-06", required_assignments=[
        dict(employee="דנה", shift=MORNING, date="2026-10-06"),
    ])
    assert [row["employee"] for row in result["assignments"]] == ["דנה"]
    assert any(row["code"] == "unfilled" for row in result["warnings"])
    assert any("הטיוטה" in note for note in result["notes"])
    assert result["metrics"]["model_calls"] == 2
    assert result["metrics"]["failed_calls"] == 1
    assert result["metrics"]["repair_error"]
    assert result["metrics"]["quality"]["unfilled_seats"] == 1


def test_focused_repair_keeps_other_days_and_their_reasons_and_sees_future_load():
    original = [assignment("2026-10-05"), assignment("2026-10-07", "יוסי")]
    model = Model([_reply(original), cover])
    result = Scheduler(model).generate_span(_week_profile(), "2026-10-05", "2026-10-07")
    repair = model.calls[1]
    assert [slot["date"] for slot in repair["period"]["slots"]] == ["2026-10-06"]
    assert {row["date"] for row in repair["already_scheduled"]} == {"2026-10-05", "2026-10-07"}
    assert {row["employee"]: row["hours"] for row in repair["fairness"]} == {
        "דנה": 8, "יוסי": 8, "רון": 0,
    }
    assert [row for row in result["assignments"] if row["date"] != "2026-10-06"] == original
    assert not result["warnings"]
    assert result["metrics"]["repair_dates"] == ["2026-10-06"]
    assert result["metrics"]["quality_before"]["unfilled_seats"] == 1
    assert result["metrics"]["quality"]["unfilled_seats"] == 0


def test_repair_that_fills_tuesday_but_breaks_wednesday_rest_is_discarded():
    profile = dict(_week_profile(), employees=[{"name": "דנה"}, {"name": "יוסי"}], shifts=[
        dict(PROFILE["shifts"][0], days=["רביעי"]),
        dict(PROFILE["shifts"][0], name="לילה", start_time="23:00", end_time="07:00", days=["שלישי"]),
    ])
    original = [assignment("2026-10-07")]
    model = Model([_reply(original), _reply([assignment("2026-10-06", shift="לילה")])])
    result = Scheduler(model).generate_span(profile, "2026-10-06", "2026-10-07")
    assert result["assignments"] == original
    assert not result["metrics"]["repair_improved"]
    assert result["metrics"]["quality"]["unfilled_seats"] == 1
    assert not any(item["code"] == "short_rest" for item in result["warnings"])


def test_repair_cannot_buy_coverage_with_new_or_worse_weekly_hour_violations():
    profile = dict(_week_profile(), employees=[
        {"name": "דנה", "max_weekly_hours": 8}, {"name": "יוסי"},
    ])
    original = [assignment("2026-10-05"), assignment("2026-10-07", "יוסי")]
    model = Model([_reply(original), _reply([assignment("2026-10-06")])])
    result = Scheduler(model).generate_span(profile, "2026-10-05", "2026-10-07")
    assert result["assignments"] == original
    assert not any(item["code"] == "over_hours" for item in result["warnings"])


def test_repair_cannot_change_frozen_dates_or_restore_rejected_candidates():
    original = [assignment("2026-10-05")]
    model = Model([_reply(original), _reply([
        assignment("2026-10-06"), assignment("2026-10-05", "רון"),
    ])])
    result = Scheduler(model).generate_span(PROFILE, "2026-10-05", "2026-10-06")
    assert result["assignments"] == original
    assert result["metrics"]["rejected"] == 1


def test_programming_errors_and_initial_failures_are_not_reported_as_saved_drafts():
    for answers, error_type in [([AgentError("אין חיבור")], AgentError),
                                ([_reply([]), RuntimeError("bug")], RuntimeError),
                                ([ModelOutputError("invalid JSON")], ModelOutputError)]:
        with pytest.raises(error_type):
            Scheduler(Model(answers)).generate_day(PROFILE, "2026-10-06")


def test_capacity_failure_splits_preview_and_carries_pins_rules_and_load():
    profile = _week_profile()
    profile["rules"] = [{"text": "העדף שיבוץ רציף", "priority": "soft"}]
    model = Model([ModelOutputError("context overflow", usage={"total_tokens": 5}), cover, cover])
    result = Scheduler(model).generate_verified(profile, "2026-10-05", "2026-10-08",
        instructions="שמור על ההעדפות", required_assignments=[
            dict(employee="דנה", shift=MORNING, date="2026-10-05"),
        ])
    assert [len(call["period"]["slots"]) for call in model.calls] == [4, 2, 2]
    assert all(call["profile"]["rules"] == profile["rules"] for call in model.calls)
    assert all(call["instructions"] == "שמור על ההעדפות" for call in model.calls)
    assert any(row["date"] == "2026-10-05" for row in result["assignments"])
    assert next(row for row in model.calls[2]["fairness"] if row["employee"] == "דנה")["hours"] == 8
    assert result["performance"]["model_calls"] == 3
    assert result["performance"]["failed_calls"] == 1
    assert result["performance"]["split_count"] == 1
    assert result["performance"]["total_tokens"] == 5
    assert result["quality"]["coverage"]["percent"] == 100


def test_ordinary_model_errors_do_not_trigger_capacity_splitting():
    model = Model([AgentError("credentials rejected")])
    with pytest.raises(AgentError):
        Scheduler(model).generate_span(PROFILE, "2026-10-05", "2026-10-08")
    assert len(model.calls) == 1


def test_audit_includes_saved_rows_beyond_the_old_200_row_prompt_bound():
    fixed = [assignment("2026-10-05", "דנה") for _ in range(201)]
    model = Model([_reply([assignment("2026-10-06", "יוסי")])])
    result = Scheduler(model).generate_day(_week_profile(), "2026-10-06", already_scheduled=fixed)
    assert result["metrics"]["quality"]["by_employee"][0]["hours"] == 201 * 8


def test_missing_commander_gets_one_focused_repair():
    profile = dict(_week_profile(), employees=[
        {"name": "דנה"}, {"name": "יוסי", "is_shift_manager": True},
    ], shifts=[dict(PROFILE["shifts"][0], requires_shift_manager=True)])
    model = Model([_reply([assignment("2026-10-06")]),
                   _reply([assignment("2026-10-06", "יוסי")])])
    result = Scheduler(model).generate_day(profile, "2026-10-06")
    assert [row["employee"] for row in result["assignments"]] == ["יוסי"]
    assert not result["warnings"]


def test_non_adjacent_repair_dates_include_the_fixed_day_between_them():
    original = [assignment("2026-10-05"), assignment("2026-10-07", "יוסי"),
                assignment("2026-10-09")]
    model = Model([_reply(original), cover])
    result = Scheduler(model).generate_span(_week_profile(), "2026-10-05", "2026-10-09")
    repair = model.calls[1]
    assert {slot["date"] for slot in repair["period"]["slots"]} == {"2026-10-06", "2026-10-08"}
    assert {row["date"] for row in repair["already_scheduled"]} == {
        "2026-10-05", "2026-10-07", "2026-10-09",
    }
    assert [row for row in result["assignments"] if row["date"] == "2026-10-07"] == [original[1]]
    assert not result["warnings"]
