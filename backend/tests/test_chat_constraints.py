"""Constraint plans: a refused row is named so the model can repair it."""

import json

import pytest

from app.bl.chat.constraints import affected_periods, normalize_constraints
from app.bl.chat.contract import RejectedPlan
from app.bl.chat.fast import ChatFastAnswers
from tests.test_manager_chat import MORNING, PROFILE, converse, setup, translation, turn

REQUEST = "תכניס אילוץ לדנה ב-2026-10-06"


def constraint(**kwargs):
    row = dict(employee="דנה", date="2026-10-06", shift="", reason="בקשת המנהל",
               available=False)
    row.update(kwargs)
    return row


def plan(*rows):
    result = turn("changes")
    result["constraints"] = list(rows)
    return result


@pytest.fixture(autouse=True)
def model_only(monkeypatch):
    # The absence reader would answer these sentences without the model.
    monkeypatch.setattr(ChatFastAnswers, "handle", lambda self, state: False)


def test_a_refused_constraint_row_is_named_and_the_repair_is_kept():
    wrong = plan(constraint(), constraint(employee="דנה כהן", date="2026-10-07"))
    fixed = plan(constraint(), constraint(date="2026-10-07"))
    repo, llm, service, chat_id, schedule_id = setup([wrong, fixed])
    message = converse(service, repo, chat_id, schedule_id, REQUEST, "repair")
    assert message["status"] == "pending"
    assert len(message["payload"]["plan"]["constraints"]) == 2
    check = json.loads(llm.calls[1]["user"])["results"][-1]
    assert check["tool"] == "plan_check" and "אילוץ 2" in check["error"]
    assert "דנה כהן" in check["error"] and "יוסי" in check["error"]


def test_unrepaired_plan_fails_saying_nothing_changed():
    repo, llm, service, chat_id, schedule_id = setup(
        [plan(constraint(shift="לילה"))] * 3)
    message = converse(service, repo, chat_id, schedule_id, REQUEST, "fail")
    assert message["status"] == "error" and len(llm.calls) == 3
    assert "\"לילה\"" in message["content"] and "לא בוצע שינוי" in message["content"]
    assert not repo.availability_rows


def test_whole_day_words_short_hours_and_repeated_rows_are_read_in_code():
    rows = normalize_constraints([
        constraint(shift="כל היום", start_time="8", end_time="12:30"),
        constraint(shift="כל היום", start_time="8", end_time="12:30"),
    ], PROFILE, [])
    assert [(row["shift"], row["start_time"], row["end_time"]) for row in rows] == \
        [("", "08:00", "12:30")]


@pytest.mark.parametrize("row, named", [
    (constraint(date="6.10"), "\"6.10\""),
    (constraint(shift="ערב"), MORNING),
    (constraint(start_time="בבוקר"), "\"בבוקר\""),
])
def test_each_refusal_says_which_value_to_fix(row, named):
    with pytest.raises(RejectedPlan, match="אילוץ 1") as refused:
        normalize_constraints([row], PROFILE, [])
    assert named in str(refused.value)


def test_two_different_updates_for_one_slot_are_still_refused():
    with pytest.raises(RejectedPlan, match="אילוץ 2"):
        normalize_constraints([constraint(), constraint(available=True)], PROFILE, [])


def test_multiple_duties_on_one_day_are_kept_as_distinct_blocking_intervals():
    rows = normalize_constraints([
        constraint(constraint_type="duty", start_time="06:00", end_time="08:00"),
        constraint(constraint_type="duty", start_time="18:00", end_time="20:00"),
    ], PROFILE, [])
    assert [(row["constraint_type"], row["start_time"], row["end_time"])
            for row in rows] == [
        ("duty", "06:00", "08:00"), ("duty", "18:00", "20:00"),
    ]


def test_a_duty_without_a_complete_interval_is_refused():
    with pytest.raises(RejectedPlan, match="start_time וגם end_time"):
        normalize_constraints([
            constraint(constraint_type="duty", start_time="06:00"),
        ], PROFILE, [])


def test_an_overnight_duty_affects_a_period_that_starts_the_next_day():
    class Repo:
        def list_schedules(self, team_id):
            return [{"id": "next", "starts_on": "2026-10-07", "ends_on": "2026-10-07"}]

        def get_schedule(self, schedule_id, team_id):
            return {"id": schedule_id}

    periods = affected_periods(Repo(), "team", [
        constraint(constraint_type="duty", start_time="22:00", end_time="06:00"),
    ])
    assert periods == [{"id": "next"}]


def test_a_cover_the_model_picked_is_left_to_the_solver_instead_of_asked_again():
    picked = turn("changes")
    picked["operations"] = [
        dict(action="remove", employee="דנה", shift=MORNING, date="2026-10-05", reason="אילוץ"),
        dict(action="assign", employee="יוסי", shift=MORNING, date="2026-10-05", reason="זמין"),
    ]
    picked["constraints"] = [constraint(date="2026-10-05")]
    repo, llm, service, chat_id, schedule_id = setup([picked, translation()])
    message = converse(service, repo, chat_id, schedule_id, "תכניס אילוץ לדנה ב-2026-10-05", "cover")
    assert message["status"] == "pending", message["content"]
    operations = message["payload"]["plan"]["operations"]
    assert [(row["action"], row["employee"]) for row in operations] == [("remove", "דנה"), ("assign", "יוסי")]
    assert "solver_note" in message["payload"]["plan"]
    assert len(llm.calls) == 1
