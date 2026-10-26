"""Constraint plans: a refused row is named so the model can repair it."""

import json

import pytest

from app.bl.chat_constraints import normalize_constraints
from app.bl.chat_contract import RejectedPlan
from app.bl.chat_fast import ChatFastAnswers
from tests.test_manager_chat import MORNING, PROFILE, converse, setup, turn

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
