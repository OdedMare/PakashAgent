"""Intro interview contract, driven by a fake model."""

import json

import pytest

from app.bl.interview import INTERVIEW_TOPICS, IntroInterview
from app.common.errors import AgentError


class _FakeLlm:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete_json(self, system, user, schema=None):
        self.calls.append({"system": system, "user": user, "schema": schema})
        return self.response


def _question_response():
    return {
        "status": "question",
        "question_id": "workplace_mission",
        "question": "על מה המשמרת אחראית?",
        "recommendation": "כדאי לתאר במשפט אחד את האחריות והתוצאה הרצויה.",
        "options": [
            {
                "id": "service",
                "label": "מתן שירות ומענה",
                "recommended": False,
            },
            {
                "id": "operations",
                "label": "רציפות תפעולית וטיפול בתקלות",
                "recommended": True,
            },
        ],
        "allow_free_text": True,
        "profile": None,
    }


def _complete_profile():
    return {
        "workplace": {
            "name": "מוקד",
            "mission": "לתת מענה",
            "success_criteria": ["רציפות"],
            "timezone": "Asia/Jerusalem",
            "operating_days": ["א-ה"],
            "planning_horizon": "שבוע",
            "scheduler_name": "שרון",
            "scheduler_works_shifts": False,
        },
        "employees": [],
        "shifts": [],
        "dependencies": [],
        "rules": [],
        "availability_process": "המנהל מעדכן",
        "constraint_deadline": "שבוע מראש",
        "casual_worker_policy": "לפי צורך ולאחר אישור זמינות",
        "training_policy": {
            "shadow_shift_fraction": 0.5,
            "shadow_shifts_per_week": 2,
            "alternate_halves": True,
            "counts_toward_staffing": False,
        },
        "rest_policy": "",
        "weekend_policy": "",
        "fairness_policy": "חלוקה מאוזנת",
        "conflict_policy": "מתריעים למנהל",
        "existing_schedule_source": "",
        "summary": "מוקד שבועי",
    }


def test_first_turn_sends_the_full_question_bank_and_returns_one_question():
    llm = _FakeLlm(_question_response())

    result = IntroInterview(llm).next_turn([])

    assert result["question"] == "על מה המשמרת אחראית?"
    assert result["allow_free_text"] is True
    assert result["options"][1]["recommended"] is True
    payload = json.loads(llm.calls[0]["user"])
    assert payload["conversation"] == []
    assert payload["topics"] == [dict(item) for item in INTERVIEW_TOPICS]
    topic_ids = {item["id"] for item in payload["topics"]}
    assert {
        "shift_vocabulary", "staffing", "qualifications", "on_call",
        "rest_and_weekend", "fairness", "conflict_policy",
    }.issubset(topic_ids)


def test_conversation_is_trimmed_and_passed_to_the_next_turn():
    llm = _FakeLlm(_question_response())
    history = [
        {"role": "assistant", "content": "  מי העובדים?  "},
        {"role": "user", "content": "  דנה ורון  "},
    ]

    IntroInterview(llm).next_turn(history)

    payload = json.loads(llm.calls[0]["user"])
    assert payload["conversation"] == [
        {"role": "assistant", "content": "מי העובדים?"},
        {"role": "user", "content": "דנה ורון"},
    ]


def test_an_ambiguous_answer_can_produce_one_follow_up_question():
    response = _question_response()
    response.update({
        "question_id": "follow_up",
        "question": "כשאתה אומר אילוץ, הוא פוסל יום שלם?",
    })

    result = IntroInterview(_FakeLlm(response)).next_turn([
        {"role": "user", "content": "אילוץ רגיל"},
    ])

    assert result["question_id"] == "follow_up"
    assert isinstance(result["question"], str)


def test_complete_turn_returns_the_confirmed_profile_and_usage():
    response = {
        "status": "complete",
        "question_id": None,
        "question": None,
        "recommendation": None,
        "options": [],
        "allow_free_text": False,
        "profile": _complete_profile(),
        "_usage": {"total_tokens": 42},
    }

    result = IntroInterview(_FakeLlm(response)).next_turn([
        {"role": "user", "content": "כן, הסיכום נכון"},
    ])

    assert result["profile"]["workplace"]["name"] == "מוקד"
    assert result["_usage"]["total_tokens"] == 42


@pytest.mark.parametrize("history", [None, {}, [{"role": "user", "content": " "}]])
def test_invalid_history_is_rejected_before_calling_the_model(history):
    llm = _FakeLlm(_question_response())
    with pytest.raises(AgentError):
        IntroInterview(llm).next_turn(history)
    assert llm.calls == []


def test_a_question_without_a_recommendation_is_rejected():
    response = _question_response()
    response["recommendation"] = None
    with pytest.raises(AgentError):
        IntroInterview(_FakeLlm(response)).next_turn([])


def test_a_question_without_selectable_answers_is_rejected():
    response = _question_response()
    response["options"] = []
    with pytest.raises(AgentError):
        IntroInterview(_FakeLlm(response)).next_turn([])


def test_only_one_answer_may_be_recommended():
    response = _question_response()
    response["options"][0]["recommended"] = True
    with pytest.raises(AgentError):
        IntroInterview(_FakeLlm(response)).next_turn([])


def test_answer_ids_are_stable_machine_readable_values():
    response = _question_response()
    response["options"][0]["id"] = "אפשרות 1"
    with pytest.raises(AgentError):
        IntroInterview(_FakeLlm(response)).next_turn([])


def test_free_text_must_remain_available_on_every_question():
    response = _question_response()
    response["allow_free_text"] = False
    with pytest.raises(AgentError):
        IntroInterview(_FakeLlm(response)).next_turn([])


def test_completion_with_a_partial_profile_is_rejected():
    response = {
        "status": "complete",
        "question_id": None,
        "question": None,
        "recommendation": None,
        "options": [],
        "allow_free_text": False,
        "profile": {"summary": "חסר"},
    }
    with pytest.raises(AgentError):
        IntroInterview(_FakeLlm(response)).next_turn([])
