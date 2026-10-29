"""The chat on a large roster: a patch names only what changes, a role stands
for its holders, and the common team questions are answered without a model."""

import copy
import datetime
import json
from unittest import mock

import app.bl.chat_tools as chat_tools
from tests.test_manager_chat import converse, setup, turn
from tests.test_schedule_api import MORNING, TEAM


def _roster(repo):
    profile = copy.deepcopy(repo.profiles[TEAM])
    profile["employees"] = [
        {"name": "דנה", "role": "מפתח", "eligible_shifts": [MORNING], "can_train": True,
         "notes": "חשוב"},
        {"name": "יוסי", "role": "מפתח", "eligible_shifts": [MORNING]},
        {"name": "רון", "role": "בודק", "eligible_shifts": [MORNING]},
    ]
    repo.profiles[TEAM] = profile
    return profile


def test_a_patch_naming_one_new_employee_keeps_everyone_else():
    proposal = turn("profile")
    proposal["profile_patch_json"] = json.dumps({"employees": [
        {"name": "מאיה", "role": "מפתח", "eligible_shifts": [MORNING],
         "rotation_group": "", "exit_pattern": "round", "service_type": "standard"},
    ]})
    repo, _, service, chat_id, schedule_id = setup([proposal])
    _roster(repo)
    message = converse(service, repo, chat_id, schedule_id, "תוסיף את מאיה")
    assert message["status"] == "pending"
    service.apply(TEAM, "manager-a", chat_id, message["id"])

    names = [row["name"] for row in repo.profiles[TEAM]["employees"]]
    assert names == ["דנה", "יוסי", "רון", "מאיה"]
    assert repo.profiles[TEAM]["employees"][0]["notes"] == "חשוב"


def test_a_recurring_constraint_patch_changes_only_that_field_of_that_person():
    rule = {"days": ["רביעי"], "shifts": [], "available": False, "is_hard": True,
            "start_time": "", "end_time": "", "reason": "לפי בקשת המנהל"}
    proposal = turn("profile")
    proposal["profile_patch_json"] = json.dumps({"employees": [
        {"name": "דנה", "recurring_constraints": [rule]}]})
    repo, _, service, chat_id, schedule_id = setup([proposal])
    _roster(repo)
    message = converse(service, repo, chat_id, schedule_id, "תוסיף לדנה אילוץ קבוע בימי רביעי")
    assert message["status"] == "pending"
    service.apply(TEAM, "manager-a", chat_id, message["id"])

    dana, yossi, ron = repo.profiles[TEAM]["employees"]
    assert dana["recurring_constraints"][0]["days"] == ["רביעי"]
    assert dana["role"] == "מפתח" and dana["can_train"] is True and dana["notes"] == "חשוב"
    assert not yossi.get("recurring_constraints") and ron["role"] == "בודק"


def test_a_constraint_naming_a_role_is_recorded_for_every_holder():
    proposal = turn("changes")
    proposal.update(stated_reason="", constraints=[dict(
        employee="", role="מפתח", date="2026-10-19", shift="", available=False,
        reason="חופש")])
    repo, _, service, chat_id, schedule_id = setup([proposal])
    _roster(repo)
    message = converse(service, repo, chat_id, schedule_id, "תוסיף לכל המפתחים חופש בשני")
    assert message["status"] == "pending"
    service.apply(TEAM, "manager-a", chat_id, message["id"])

    assert sorted(row["employee"] for row in repo.availability_rows) == ["דנה", "יוסי"]


def test_an_unknown_role_is_refused_with_the_real_roles_named():
    from app.bl.chat_constraints import normalize_constraints
    from app.bl.chat_contract import RejectedPlan
    profile = {"employees": [{"name": "דנה", "role": "מפתח"}], "shifts": []}
    try:
        normalize_constraints([dict(employee="", role="מעצב", date="2026-10-19", shift="")],
                              profile, [])
    except RejectedPlan as refusal:
        assert "מפתח" in str(refusal)
    else:
        raise AssertionError("an unknown role was accepted")


def test_who_works_today_is_answered_without_a_model_round():
    repo, llm, service, chat_id, schedule_id = setup([])
    with mock.patch.object(chat_tools, "israel_today", return_value=datetime.date(2026, 10, 5)):
        message = converse(service, repo, chat_id, schedule_id, "מי עובד היום")

    assert message["status"] == "complete"
    assert "דנה" in message["content"] and MORNING in message["content"]
    assert [step["tool"] for step in message["payload"]["steps"]] == ["who_works"]
    assert message["payload"]["_usage"]["model_rounds"] == 0


def test_a_question_naming_a_person_is_left_to_the_model():
    answer = turn("answer")
    answer["reply"] = "דנה עובדת עם יוסי"
    repo, llm, service, chat_id, schedule_id = setup([answer])
    with mock.patch.object(chat_tools, "israel_today", return_value=datetime.date(2026, 10, 5)):
        message = converse(service, repo, chat_id, schedule_id, "מי עובד עם דנה היום")

    assert message["content"] == "דנה עובדת עם יוסי"
