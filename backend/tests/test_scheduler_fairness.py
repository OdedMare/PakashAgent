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


def night_profile():
    return dict(profile(), shifts=[dict(profile()["shifts"][0], name="משמרת ג",
                                       start_time="23:00", end_time="07:00")])


def night(day, employee="דנה"):
    return assignment("2026-10-%02d" % day, employee, "משמרת ג")


@pytest.mark.parametrize("method", ["generate", "generate_span"])
def test_two_nights_against_zero_gets_repaired_even_below_the_hours_threshold(method):
    original, balanced = [night(5), night(6)], [night(5), night(6, "יוסי")]
    model = Model([_reply(original), _reply(balanced)])
    result = getattr(Scheduler(model), method)(night_profile(), "2026-10-05", "2026-10-06")
    assert result["assignments"] == balanced
    assert len(model.calls) == 2
    assert all(slot["is_night"] for slot in model.calls[0]["period"]["slots"])
    assert "פער לילות" in model.calls[1]["repair"]["warnings"][0]
    if method == "generate_span":
        assert not result["warnings"]


def test_balanced_hours_still_require_night_repair_through_a_day_night_exchange():
    workplace = night_profile()
    workplace["shifts"][0]["days"] = ["שני", "רביעי"]
    workplace["shifts"].append(dict(profile()["shifts"][0], days=["שלישי", "חמישי"]))
    original = [night(5), assignment("2026-10-06", "יוסי"),
                night(7), assignment("2026-10-08", "יוסי")]
    balanced = [night(5, "יוסי"), assignment("2026-10-06"),
                night(7), assignment("2026-10-08", "יוסי")]
    model = Model([_reply(original), _reply(balanced)])
    result = Scheduler(model).generate_span(workplace, "2026-10-05", "2026-10-08")
    assert result["assignments"] == balanced
    assert not result["warnings"]
    assert len(model.calls) == 2
    assert {row["hours"] for row in result["metrics"]["quality"]["by_employee"]} == {16}


@pytest.mark.parametrize("method", ["generate", "generate_span"])
def test_one_extra_night_is_unavoidable_when_the_number_of_seats_is_odd(method):
    balanced = [night(5), night(6, "יוסי"), night(7)]
    model = Model([_reply(balanced)])
    result = getattr(Scheduler(model), method)(night_profile(), "2026-10-05", "2026-10-07")
    assert result["assignments"] == balanced
    assert len(model.calls) == 1


@pytest.mark.parametrize("method", ["generate", "generate_span"])
def test_history_breaks_a_tie_between_equally_balanced_current_night_loads(method):
    model = Model([_reply([night(5)]), _reply([night(5, "יוסי")])])
    result = getattr(Scheduler(model), method)(night_profile(), "2026-10-05", "2026-10-05",
        history=[assignment("2026-09-%02d" % day, "דנה", "משמרת ג") for day in range(1, 4)])
    assert result["assignments"] == [night(5, "יוסי")]
    assert len(model.calls) == 2


def test_historical_imbalance_does_not_concentrate_the_current_period_nights():
    balanced = [night(5), night(6, "יוסי")]
    model = Model([_reply([night(5), night(6)]), _reply(balanced)])
    result = Scheduler(model).generate_span(night_profile(), "2026-10-05", "2026-10-06",
        history=[assignment("2026-09-%02d" % day, "יוסי", "משמרת ג") for day in range(1, 5)])
    assert result["assignments"] == balanced
    assert not result["warnings"]


def test_four_night_seats_among_three_workers_reach_the_smallest_possible_maximum():
    workplace = night_profile()
    workplace["employees"].append({"name": "רון"})
    balanced = [night(5), night(6, "יוסי"), night(7, "רון"), night(8)]
    model = Model([_reply([night(day) for day in range(5, 9)]), _reply(balanced)])
    result = Scheduler(model).generate_span(workplace, "2026-10-05", "2026-10-08")
    loads = load_history(result["assignments"], workplace["shifts"], workplace["employees"])
    assert sorted(row["nights"] for row in loads) == [1, 1, 2]
    assert not result["warnings"]


def test_required_night_stays_fixed_while_the_other_night_moves():
    pinned = [night(5)]
    model = Model([_reply([night(5), night(6)]), _reply([night(6, "יוסי")])])
    result = Scheduler(model).generate_span(night_profile(), "2026-10-05", "2026-10-06",
                                            required_assignments=pinned)
    assert [(row["employee"], row["date"]) for row in result["assignments"]] == [
        ("דנה", "2026-10-05"), ("יוסי", "2026-10-06"),
    ]
    assert not result["warnings"]


@pytest.mark.parametrize("restriction", ["unavailable", "ineligible", "pinned", "rest", "hours"])
def test_unavoidable_night_gaps_do_not_trigger_an_impossible_repair(restriction):
    workplace, options = night_profile(), {}
    original = [night(5), night(6)]
    if restriction == "unavailable":
        options["availability"] = [dict(employee="יוסי", date=row["date"], available=False)
                                   for row in original]
    elif restriction == "ineligible":
        workplace["employees"][1]["eligible_shifts"] = [MORNING]
    elif restriction == "pinned":
        options["required_assignments"] = original
    elif restriction == "hours":
        workplace["employees"][1]["max_weekly_hours"] = 4
    else:
        workplace["shifts"].append(dict(profile()["shifts"][0]))
        options["already_scheduled"] = [assignment("2026-10-06", "יוסי"),
                                        assignment("2026-10-07", "יוסי")]
        original.append(assignment("2026-10-06", "יוסי"))
        options["required_assignments"] = [assignment("2026-10-06", "יוסי")]
        # The unfilled Monday morning is intentionally outside this request.
        workplace["shifts"][1]["days"] = ["שלישי", "רביעי"]
    model = Model([_reply(original)])
    result = Scheduler(model).generate_span(workplace, "2026-10-05", "2026-10-06", **options)
    assert len(model.calls) == 1
    assert not any(item["code"] == "uneven_nights" for item in result["warnings"])


@pytest.mark.parametrize("repair", ["unchanged", "short_rest", "unfilled", "failed"])
def test_unsuccessful_night_repair_preserves_the_draft_and_reports_remaining_gap(repair):
    original = [night(5), night(6)]
    if repair == "failed":
        second = AgentError("המודל אינו זמין")
    elif repair == "unfilled":
        second = _reply([night(5)])
    elif repair == "short_rest":
        second = _reply([night(5), night(6, "יוסי")])
    else:
        second = _reply(original)
    options = {"already_scheduled": [assignment("2026-10-07", "יוסי", "משמרת יום")]}
    workplace = night_profile()
    workplace["shifts"].append(dict(profile()["shifts"][0], name="משמרת יום", days=["רביעי"]))
    model = Model([_reply(original), second])
    result = Scheduler(model).generate_span(workplace, "2026-10-05", "2026-10-06", **options)
    assert result["assignments"] == original
    assert any(item["code"] == "uneven_nights" for item in result["warnings"])
    assert any("פער לילות" in note for note in result["notes"])
    assert not result["metrics"]["repair_improved"]
