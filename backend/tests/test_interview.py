"""Intro interview contract, driven by a fake model.

The turn shape is the `plan-chat` one ported from AiSummryIO: one question
per turn carrying a recommendation and clickable options, plus the draft
profile so far. Where the old contract raised on a malformed turn, this one
normalizes — a dropped option is better than a dead interview — so most of
these assert what survives rather than that an error was raised. The two
things still enforced in code are the ready-gate and the draft merge.
"""

import json

import pytest

from app.bl.interview import INTERVIEW_TOPICS, IntroInterview, empty_draft
from app.common.errors import AgentError


class _FakeLlm:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete_json(self, system, user, schema=None, flow=""):
        self.calls.append({"system": system, "user": user, "schema": schema})
        return self.response


def _question_response(**overrides):
    response = {
        "reply": "תודה, רשמתי.",
        "question": {
            "question": "על מה המשמרת אחראית?",
            "recommendation": "כדאי לתאר במשפט אחד את האחריות והתוצאה.",
            "why": "בלי זה אי אפשר לדעת מה נחשב משמרת מוצלחת.",
            "options": [
                {
                    "label": "רציפות תפעולית",
                    "answer": "המשמרת אחראית על רציפות תפעולית וטיפול בתקלות.",
                },
                {
                    "label": "מתן שירות",
                    "answer": "המשמרת אחראית על מתן שירות ומענה ללקוחות.",
                },
            ],
        },
        "resolved": ["שם מקום העבודה: מוקד"],
        "open_points": ["עדיין לא הוגדרו סוגי המשמרות."],
        "awaiting_confirmation": False,
        "ready": False,
        "draft": empty_draft(),
    }
    response.update(overrides)
    return response


def _complete_profile():
    return dict(empty_draft(), **{
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
        "employees": [{"name": "דנה", "role": "נציגה"}],
        "shifts": [{"name": "בוקר", "start_time": "08:00"}],
        "rules": [{"text": "אין בוקר אחרי לילה", "priority": "hard"}],
        "availability_process": "המנהל מעדכן",
        "constraint_deadline": "שבוע מראש",
        "summary": "מוקד שבועי",
    })


def test_first_turn_sends_the_topics_and_returns_one_question():
    llm = _FakeLlm(_question_response())

    result = IntroInterview(llm).next_turn([])

    assert result["question"]["question"] == "על מה המשמרת אחראית?"
    assert result["question"]["recommendation"]
    assert result["question"]["why"]
    assert len(result["question"]["options"]) == 2
    payload = json.loads(llm.calls[0]["user"])
    assert payload["conversation"] == []
    assert payload["draft_so_far"] == {}
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


def test_the_draft_so_far_is_handed_back_to_the_model():
    llm = _FakeLlm(_question_response())
    draft = dict(empty_draft(), summary="מוקד שבועי")

    IntroInterview(llm).next_turn([], draft)

    payload = json.loads(llm.calls[0]["user"])
    assert payload["draft_so_far"]["summary"] == "מוקד שבועי"


@pytest.mark.parametrize(
    "history",
    [None, {}, [{"role": "user", "content": 7}], [{"role": "system", "content": "x"}]],
)
def test_invalid_history_is_rejected_before_calling_the_model(history):
    llm = _FakeLlm(_question_response())
    with pytest.raises(AgentError):
        IntroInterview(llm).next_turn(history)
    assert llm.calls == []


def test_an_empty_stored_message_is_skipped_rather_than_wedging_the_interview():
    """A turn the model returned without prose must not end the interview.

    The manager's own blank submission is refused by the service, so anything
    empty arriving here came out of the store — and raising over it would fail
    identically on every later turn, leaving a session that can never be
    answered again.
    """
    llm = _FakeLlm(_question_response())
    history = [
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "דנה ורון"},
        {"role": "assistant", "content": "   "},
    ]

    IntroInterview(llm).next_turn(history)

    payload = json.loads(llm.calls[0]["user"])
    assert payload["conversation"] == [{"role": "user", "content": "דנה ורון"}]


# --- the draft merge -------------------------------------------------------


def test_a_field_settled_earlier_survives_a_turn_that_omits_it():
    """The model rebuilds the draft each turn; a narrow answer must not blank
    the twenty fields it did not mention."""
    previous = dict(empty_draft(), **{
        "workplace": {"name": "מוקד", "mission": "מענה"},
        "employees": [{"name": "דנה"}],
        "summary": "מוקד שבועי",
    })
    response = _question_response(draft=empty_draft())

    result = IntroInterview(_FakeLlm(response)).next_turn([], previous)

    assert result["draft"]["workplace"]["name"] == "מוקד"
    assert result["draft"]["employees"] == [{"name": "דנה"}]
    assert result["draft"]["summary"] == "מוקד שבועי"


def test_a_restated_field_overrides_what_was_agreed_before():
    """Carrying forward must not freeze a value: a correction is exactly the
    case where the manager restates a field."""
    previous = dict(empty_draft(), summary="ישן")
    response = _question_response(draft=dict(empty_draft(), summary="חדש"))

    result = IntroInterview(_FakeLlm(response)).next_turn([], previous)

    assert result["draft"]["summary"] == "חדש"


def test_workplace_is_merged_per_key_not_as_one_blob():
    """`workplace` holds eight fields settled across different turns, so the
    last turn to mention it must not be the only one that counts."""
    previous = dict(empty_draft(), workplace={"name": "מוקד", "mission": "מענה"})
    response = _question_response(
        draft=dict(empty_draft(), workplace={"planning_horizon": "שבוע"})
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([], previous)

    assert result["draft"]["workplace"] == {
        "name": "מוקד", "mission": "מענה", "planning_horizon": "שבוע",
    }


# --- the ready gate --------------------------------------------------------


def test_a_turn_that_still_asks_is_never_ready():
    """`ready` unlocks writing the profile, so a model that mislabels an open
    question must not be believed."""
    response = _question_response(ready=True, draft=_complete_profile())

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["ready"] is False


def test_the_confirmation_turn_is_not_yet_ready():
    """The summary is presented for approval; readiness comes the turn after
    the manager confirms it."""
    response = _question_response(
        question=None, awaiting_confirmation=True, ready=True,
        draft=_complete_profile(),
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["awaiting_confirmation"] is True
    assert result["ready"] is False


def test_an_open_question_withdraws_the_confirmation_flag():
    response = _question_response(awaiting_confirmation=True)

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["awaiting_confirmation"] is False


def test_a_confirmed_complete_profile_is_ready():
    response = _question_response(
        question=None, awaiting_confirmation=False, ready=True,
        draft=_complete_profile(), reply="מצוין, סיימנו.",
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([
        {"role": "user", "content": "כן, הסיכום נכון"},
    ])

    assert result["ready"] is True
    assert result["draft"]["workplace"]["name"] == "מוקד"


def test_a_profile_missing_a_required_topic_is_not_ready():
    """The scheduler cannot run without shifts, so a model that calls a
    shiftless profile finished is overruled and the gap resurfaces."""
    partial = dict(_complete_profile(), shifts=[])
    response = _question_response(
        question=None, awaiting_confirmation=False, ready=True, draft=partial,
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["ready"] is False
    assert "לא הוגדר אף סוג משמרת." in result["open_points"]


def test_usage_rides_through_the_turn():
    response = _question_response(_usage={"total_tokens": 42})

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["_usage"]["total_tokens"] == 42


# --- option normalization --------------------------------------------------


def test_an_option_without_a_sendable_answer_is_dropped():
    """A clicked option is sent verbatim as the manager's message, so one
    with no `answer` has nothing to send."""
    response = _question_response()
    response["question"]["options"].append({"label": "אולי", "answer": ""})

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert [item["label"] for item in result["question"]["options"]] == [
        "רציפות תפעולית", "מתן שירות",
    ]


def test_a_lone_option_is_dropped_because_one_option_is_not_a_choice():
    response = _question_response()
    response["question"]["options"] = [
        {"label": "כן", "answer": "כן, זה נכון."},
    ]

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["question"]["options"] == []


def test_options_are_capped_and_deduplicated():
    response = _question_response()
    response["question"]["options"] = [
        {"label": "א", "answer": "תשובה א"},
        {"label": "א", "answer": "תשובה א שוב"},
        {"label": "ב", "answer": "תשובה ב"},
        {"label": "ג", "answer": "תשובה ג"},
        {"label": "ד", "answer": "תשובה ד"},
        {"label": "ה", "answer": "תשובה ה"},
    ]

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    labels = [item["label"] for item in result["question"]["options"]]
    assert labels == ["א", "ב", "ג", "ד"]


def test_a_blank_question_reads_as_no_question():
    response = _question_response()
    response["question"]["question"] = "   "

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["question"] is None


def test_a_non_dict_model_reply_is_rejected():
    with pytest.raises(AgentError):
        IntroInterview(_FakeLlm("not json")).next_turn([])
