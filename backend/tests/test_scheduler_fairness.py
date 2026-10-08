"""Large avoidable hour gaps get one model repair, on both generation paths."""

import pytest

from app.bl.audit import load_history
from app.bl.scheduler import Scheduler
from app.common.errors.errors import AgentError
from tests.test_scheduler import MORNING, _reply, _week_profile
from tests.test_scheduler_recovery import Model, assignment, cover


def profile():
    return dict(_week_profile(), employees=[{"name": "דנה"}, {"name": "יוסי"}])


def overloaded():
    return [assignment("2026-10-%02d" % day) for day in range(5, 10)]


@pytest.mark.parametrize("method", ["generate", "generate_span"])
def test_forty_hours_against_zero_gets_one_balanced_repair(method):
    workplace = profile()
    balanced = [assignment(row["date"], "דנה" if index < 3 else "יוסי")
                for index, row in enumerate(overloaded())]
    model = Model([_reply(overloaded(), summary="סידור ראשוני"),
                   _reply(balanced, summary="סידור מאוזן")])
    result = getattr(Scheduler(model), method)(workplace, "2026-10-05", "2026-10-09")
    hours = sorted(row["hours"] for row in load_history(
        result["assignments"], workplace["shifts"], workplace["employees"]))
    assert hours == [16, 24]
    assert len(model.calls) == 2
    assert len(result["assignments"]) == 5
    assert result["assignments"] == balanced  # Includes two consecutive days off.
    assert result["summary"] == "סידור מאוזן"
    assert len(model.calls[1]["period"]["slots"]) == 5
    assert "40" in model.calls[1]["repair"]["warnings"][0]


@pytest.mark.parametrize("method", ["generate", "generate_span"])
def test_history_is_separate_from_current_period_load_and_pins(method):
    model = Model([_reply(overloaded()), cover])
    result = getattr(Scheduler(model), method)(profile(), "2026-10-05", "2026-10-09",
        history=[assignment("2026-09-%02d" % day, "יוסי") for day in range(1, 6)],
        required_assignments=[dict(employee="דנה", date="2026-10-05", shift=MORNING)])
    payload = model.calls[0]
    assert {row["employee"]: row["hours"] for row in payload["fairness"]} == {
        "דנה": 8, "יוסי": 40,
    }
    assert {row["employee"]: row["hours"] for row in payload["period_load"]} == {
        "דנה": 8, "יוסי": 0,
    }
    assert next(row for row in result["assignments"] if row["date"] == "2026-10-05")["employee"] == "דנה"
    assert any(row["employee"] == "יוסי" for row in result["assignments"])


@pytest.mark.parametrize("restriction", ["unavailable", "ineligible", "commander", "role", "trainee", "pinned"])
def test_zero_hours_for_someone_who_cannot_replace_the_worker_does_not_buy_a_repair(restriction):
    workplace, options = profile(), {}
    if restriction == "unavailable":
        options["availability"] = [dict(employee="יוסי", date=row["date"], available=False)
                                   for row in overloaded()]
    elif restriction == "ineligible":
        workplace["employees"][1]["eligible_shifts"] = ["לילה"]
    elif restriction == "commander":
        workplace["shifts"][0]["requires_shift_manager"] = True
        workplace["employees"][0]["is_shift_manager"] = True
    elif restriction == "role":
        workplace["shifts"][0]["staffing"][0]["required_roles"] = ["חובש"]
        workplace["employees"][0]["role"] = "חובש"
    elif restriction == "trainee":
        workplace["employees"][1]["is_trainee"] = True
    else:
        options["required_assignments"] = overloaded()
    model = Model([_reply(overloaded())])
    result = Scheduler(model).generate_span(workplace, "2026-10-05", "2026-10-09", **options)
    assert len(model.calls) == 1
    assert not result["warnings"]


@pytest.mark.parametrize("repair", ["unchanged", "unfilled", "over_hours", "failed"])
def test_a_bad_fairness_repair_keeps_the_audited_original(repair):
    workplace = profile()
    if repair == "unchanged":
        second = _reply(overloaded())
    elif repair == "unfilled":
        second = _reply([assignment("2026-10-05")])
    elif repair == "over_hours":
        workplace["employees"][1]["max_weekly_hours"] = 8
        second = _reply([assignment(row["date"], "יוסי" if index < 2 else "דנה")
                         for index, row in enumerate(overloaded())])
    else:
        second = AgentError("המודל אינו זמין")
    model = Model([_reply(overloaded()), second])
    result = Scheduler(model).generate_span(workplace, "2026-10-05", "2026-10-09")
    assert result["assignments"] == overloaded()
    assert len(model.calls) == 2
    assert any(item["code"] == "uneven_load" for item in result["warnings"])
    assert not result["metrics"]["repair_improved"]


def test_fixed_future_hours_and_overnight_weights_are_counted_in_the_payload():
    workplace = profile()
    workplace["shifts"][0].update(start_time="23:00", end_time="07:00", hour_weight=0.5)
    model = Model([_reply([assignment("2026-10-06", "יוסי")])])
    Scheduler(model).generate_day(workplace, "2026-10-06",
                                  already_scheduled=[assignment("2026-10-08")])
    assert model.calls[0]["period"]["slots"][0]["hours"] == 4
    assert {row["employee"]: row["hours"] for row in model.calls[0]["period_load"]} == {
        "דנה": 4, "יוסי": 0,
    }


def test_coverage_repair_has_priority_even_when_it_cannot_improve_fairness():
    workplace = dict(profile(), audit_policy={"max_weekly_hours": 60})
    complete = overloaded() + [assignment("2026-10-10")]
    model = Model([_reply(overloaded()), _reply(complete)])
    result = Scheduler(model).generate_span(workplace, "2026-10-05", "2026-10-10")
    assert result["assignments"] == complete
    assert not any(item["code"] == "unfilled" for item in result["warnings"])
    assert any(item["code"] == "uneven_load" for item in result["warnings"])
    assert any("פער עומס" in note for note in result["notes"])
