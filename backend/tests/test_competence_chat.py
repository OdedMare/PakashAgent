"""Raising, lowering and setting competence from the chat, with no model."""

import pytest

from app.bl.competence import read, shifted
from tests.test_manager_chat import TEAM, converse, setup

ROSTER = ["דנה", "יוסי", "דן"]


@pytest.mark.parametrize("sentence, expected", [
    ("תעלה את הכשירות של יוסי", dict(names=["יוסי"], step=1)),
    ("תוריד כשירות לדנה ויוסי", dict(names=["דנה", "יוסי"], step=-1)),
    ("הכשירות של דנה מצטיינת", dict(names=["דנה"], level="excellent")),
    ("תעלה את הכשירות של דן לגבוהה", dict(names=["דן"], level="high")),
    ("קבע כשירות חלשה לדנה", dict(names=["דנה"], level="weak")),
    ("קבע רמה מקצועית גבוהה לדנה", dict(names=["דנה"], level="high")),
    ("תעלה את הרמה המקצועית של יוסי", dict(names=["יוסי"], step=1)),
    ("תמחק את הכשירות של יוסי", dict(names=["יוסי"], level="")),
])
def test_a_competence_sentence_is_read(sentence, expected):
    assert read(sentence, ROSTER) == expected


@pytest.mark.parametrize("sentence", [
    "תעלה את יוסי למשמרת בוקר",          # no competence
    "תעלה את הכשירות",                    # nobody named
    "האם יוסי בכשירות גבוהה?",            # a question
    "מי בכשירות חלשה",
    "מה הרמה המקצועית של יוסי",
    "תעלה ותוריד כשירות ליוסי",           # both ways
])
def test_anything_else_is_left_to_the_model(sentence):
    assert read(sentence, ROSTER) is None


def test_a_step_stops_at_either_end_and_needs_a_level_to_start_from():
    assert shifted("medium", 1) == "high"
    assert shifted("weak", -1) is None
    assert shifted("excellent", 1) is None
    assert shifted("", 1) is None


def test_raising_competence_is_a_profile_plan_that_applies_on_approval():
    repo, llm, service, chat_id, schedule_id = setup([])
    repo.profiles[TEAM]["employees"][0]["competence"] = "medium"
    name = repo.profiles[TEAM]["employees"][0]["name"]
    message = converse(service, repo, chat_id, schedule_id, "תעלה את הכשירות של %s" % name)
    assert message["status"] == "pending" and message["payload"]["fast_path"] == "competence"
    assert message["payload"]["plan"]["kind"] == "profile"
    assert repo.profiles[TEAM]["employees"][0]["competence"] == "medium"
    service.apply(TEAM, "manager-a", chat_id, message["id"])
    updated = repo.profiles[TEAM]["employees"]
    assert updated[0]["competence"] == "high"
    assert not llm.calls


def test_an_unrated_soldier_is_asked_for_a_level_and_a_button_plans_it():
    repo, llm, service, chat_id, schedule_id = setup([])
    name = repo.profiles[TEAM]["employees"][0]["name"]
    asked = converse(service, repo, chat_id, schedule_id, "תוריד כשירות ל%s" % name)
    assert asked["status"] == "complete" and "לאיזו רמה" in asked["content"]
    options = asked["payload"]["question"]["options"]
    assert [option["label"] for option in options] == ["חלשה", "בינונית", "גבוהה", "מצטיינת"]
    planned = converse(service, repo, chat_id, schedule_id, options[0]["answer"], "pick")
    assert planned["status"] == "pending"
    after = planned["payload"]["plan"]["profile_after"]["employees"]
    assert next(row for row in after if row["name"] == name)["competence"] == "weak"
    typed = converse(service, repo, chat_id, schedule_id, "תוריד כשירות ל%s" % name, "again")
    short = converse(service, repo, chat_id, schedule_id, "בינונית", "short")
    assert typed["status"] == "complete" and short["status"] == "pending"
    assert not llm.calls


def test_the_top_level_is_not_raised_further():
    repo, llm, service, chat_id, schedule_id = setup([])
    repo.profiles[TEAM]["employees"][0]["competence"] = "excellent"
    name = repo.profiles[TEAM]["employees"][0]["name"]
    message = converse(service, repo, chat_id, schedule_id, "תעלה את הכשירות של %s" % name)
    assert message["status"] == "complete" and "הגבוהה ביותר" in message["content"]
    assert not llm.calls
