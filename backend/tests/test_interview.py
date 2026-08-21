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
        "draft_update": {},
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
    assert payload["recent_conversation"] == []
    assert payload["draft_so_far"] == {}
    assert payload["topics"] == [dict(item) for item in INTERVIEW_TOPICS]
    topic_ids = {item["id"] for item in payload["topics"]}
    assert {
        "shift_vocabulary", "staffing", "qualifications", "on_call",
        "rest_and_weekend", "fairness", "conflict_policy",
    }.issubset(topic_ids)


def test_the_recent_conversation_is_passed_to_the_next_turn():
    llm = _FakeLlm(_question_response())
    history = [
        {"role": "assistant", "content": "מה שם המקום?"},
        {"role": "user", "content": "מוקד"},
        {"role": "assistant", "content": "  מי העובדים?  "},
        {"role": "user", "content": "  דנה ורון  "},
    ]

    IntroInterview(llm).next_turn(history)

    payload = json.loads(llm.calls[0]["user"])
    assert payload["recent_conversation"] == [
        {"role": "assistant", "content": "מה שם המקום?"},
        {"role": "user", "content": "מוקד"},
        {"role": "assistant", "content": "מי העובדים?"},
        {"role": "user", "content": "דנה ורון"},
    ]


def test_the_conversation_window_is_bounded():
    """Bounded, but wide enough that the model can see what it already asked.

    A single exchange is what made the interview circle: the draft records
    settled facts and never records which questions were put, so a model
    reading only the last answer cannot tell a fresh topic from one it just
    covered.
    """
    llm = _FakeLlm(_question_response())
    history = [
        {"role": "assistant" if index % 2 == 0 else "user",
         "content": "הודעה {}".format(index)}
        for index in range(40)
    ]

    IntroInterview(llm).next_turn(history)

    conversation = json.loads(llm.calls[0]["user"])["recent_conversation"]
    assert len(conversation) == 12
    assert conversation[-1] == {"role": "user", "content": "הודעה 39"}


def test_every_question_already_asked_is_listed_for_the_model():
    """The anti-repetition list: what was *asked*, not what was settled.

    `resolved` records answers. A question the manager deflected settles
    nothing and so never lands there — which is precisely the question a
    model working from settled facts alone asks a second time.
    """
    llm = _FakeLlm(_question_response())
    history = [
        {"role": "assistant", "content": "מה שם המקום?"},
        {"role": "user", "content": "מוקד"},
        {"role": "assistant", "content": "מי העובדים?"},
        {"role": "user", "content": "אחר כך"},
    ]

    IntroInterview(llm).next_turn(history)

    payload = json.loads(llm.calls[0]["user"])
    assert payload["questions_already_asked"] == [
        "מה שם המקום?", "מי העובדים?",
    ]


def test_questions_already_asked_survive_falling_out_of_the_window():
    """A topic covered thirty turns ago must still not be re-asked."""
    llm = _FakeLlm(_question_response())
    history = [{"role": "assistant", "content": "מה שם המקום?"}]
    history += [
        {"role": "assistant" if index % 2 == 0 else "user",
         "content": "הודעה {}".format(index)}
        for index in range(40)
    ]

    IntroInterview(llm).next_turn(history)

    payload = json.loads(llm.calls[0]["user"])
    assert "מה שם המקום?" not in [
        message["content"] for message in payload["recent_conversation"]
    ]
    assert payload["questions_already_asked"][0] == "מה שם המקום?"


def test_structured_state_replaces_the_old_conversation_context():
    llm = _FakeLlm(_question_response())

    IntroInterview(llm).next_turn([], {}, {
        "resolved": ["שם מקום העבודה: מוקד"],
        "open_points": ["חסרים עובדים"],
    })

    payload = json.loads(llm.calls[0]["user"])
    assert payload["resolved_so_far"] == ["שם מקום העבודה: מוקד"]
    assert payload["open_points_so_far"] == ["חסרים עובדים"]


def test_model_schema_accepts_a_sparse_draft_update():
    llm = _FakeLlm(_question_response())

    IntroInterview(llm).next_turn([])

    update = llm.calls[0]["schema"]["properties"]["draft_update"]
    assert "required" not in update
    assert "required" not in update["properties"]["workplace"]


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
    assert payload["recent_conversation"] == [
        {"role": "user", "content": "דנה ורון"}
    ]


# --- the draft merge -------------------------------------------------------


def test_a_field_settled_earlier_survives_a_turn_that_omits_it():
    """The model rebuilds the draft each turn; a narrow answer must not blank
    the twenty fields it did not mention."""
    previous = dict(empty_draft(), **{
        "workplace": {"name": "מוקד", "mission": "מענה"},
        "employees": [{"name": "דנה"}],
        "summary": "מוקד שבועי",
    })
    response = _question_response(draft_update={})

    result = IntroInterview(_FakeLlm(response)).next_turn([], previous)

    assert result["draft"]["workplace"]["name"] == "מוקד"
    assert result["draft"]["employees"] == [{"name": "דנה"}]
    assert result["draft"]["summary"] == "מוקד שבועי"


def test_a_restated_field_overrides_what_was_agreed_before():
    """Carrying forward must not freeze a value: a correction is exactly the
    case where the manager restates a field."""
    previous = dict(empty_draft(), summary="ישן")
    response = _question_response(draft_update={"summary": "חדש"})

    result = IntroInterview(_FakeLlm(response)).next_turn([], previous)

    assert result["draft"]["summary"] == "חדש"


def test_workplace_is_merged_per_key_not_as_one_blob():
    """`workplace` holds eight fields settled across different turns, so the
    last turn to mention it must not be the only one that counts."""
    previous = dict(empty_draft(), workplace={"name": "מוקד", "mission": "מענה"})
    response = _question_response(
        draft_update={"workplace": {"planning_horizon": "שבוע"}}
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([], previous)

    assert result["draft"]["workplace"] == {
        "name": "מוקד", "mission": "מענה", "planning_horizon": "שבוע",
    }


# --- the ready gate --------------------------------------------------------


def test_a_turn_that_still_asks_is_never_ready():
    """`ready` unlocks writing the profile, so a model that mislabels an open
    question must not be believed."""
    response = _question_response(ready=True, draft_update=_complete_profile())

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["ready"] is False


def test_the_confirmation_turn_is_not_yet_ready():
    """The summary is presented for approval; readiness comes the turn after
    the manager confirms it."""
    response = _question_response(
        question=None, awaiting_confirmation=True, ready=True,
        draft_update=_complete_profile(),
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
        draft_update=_complete_profile(), reply="מצוין, סיימנו.",
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
        question=None, awaiting_confirmation=False, ready=True,
        draft_update=partial,
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["ready"] is False
    assert "לא הוגדר אף סוג משמרת." in result["open_points"]


def test_usage_rides_through_the_turn():
    response = _question_response(_usage={"total_tokens": 42})

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["_usage"]["total_tokens"] == 42


# --- the open points and resolved lists ------------------------------------


def test_an_echoed_missing_topic_is_not_listed_twice():
    """The repetition the manager sees in "נשאר לסגור".

    `missing_topics` sentences are handed to the model as `open_points_so_far`
    every turn, so a model carrying forward what is still open returns them —
    and the code-generated copy was then appended beside the echo. That
    repeats for as long as the gap stays open, which is every turn until it
    is filled.
    """
    response = _question_response(
        open_points=["לא נרשם אף עובד.", "חסרה רשימת האילוצים"],
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    points = result["open_points"]
    assert points.count("לא נרשם אף עובד.") == 1
    assert len(points) == len(set(points))


def test_the_model_repeating_its_own_open_point_is_collapsed():
    response = _question_response(
        open_points=["חסרה רשימת האילוצים", "חסרה רשימת האילוצים  "],
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["open_points"].count("חסרה רשימת האילוצים") == 1


def test_a_repeated_resolved_line_is_collapsed():
    response = _question_response(resolved=["שם: מוקד", "שם: מוקד"])

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["resolved"] == ["שם: מוקד"]


def test_open_points_keep_the_agents_own_order():
    """Deduplicated in place, never sorted: the panel is read top to bottom
    and the agent's ordering carries what it thinks matters most."""
    response = _question_response(open_points=["ג", "א", "ב", "א"])

    result = IntroInterview(_FakeLlm(response)).next_turn([])

    assert result["open_points"][:3] == ["ג", "א", "ב"]


# --- a promise that recorded nothing ---------------------------------------


def test_a_reply_promising_an_update_that_records_nothing_is_flagged():
    """"אני מעדכן את המדיניות" while `draft_update` is empty.

    `reply` is prose and stores nothing; `draft_update` is what the server
    keeps. A turn that announces an update it did not make has dropped what
    the manager just said, and without this they have no way to see it.
    """
    response = _question_response(
        reply="אני מעדכן את המדיניות", draft_update={},
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([], empty_draft())

    assert any("לא נשמרה" in line for line in result["open_points"])


def test_a_promise_that_actually_records_is_not_flagged():
    response = _question_response(
        reply="אני מעדכן את המדיניות",
        draft_update={"rest_policy": "שמונה שעות מנוחה"},
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([], empty_draft())

    assert not any("לא נשמרה" in line for line in result["open_points"])


def test_an_ordinary_turn_that_settles_nothing_is_not_flagged():
    """An empty `draft_update` is normal on its own.

    A turn that only asks a clarifying question settles no fact and should
    change no field, so the empty update alone must never be reported — only
    an empty update underneath prose that claimed otherwise.
    """
    response = _question_response(reply="תודה. שאלה נוספת:", draft_update={})

    result = IntroInterview(_FakeLlm(response)).next_turn([], empty_draft())

    assert not any("לא נשמרה" in line for line in result["open_points"])


def test_re_sending_an_unchanged_value_still_counts_as_recording_nothing():
    draft = dict(empty_draft(), summary="קיים")
    response = _question_response(
        reply="אני שומר את זה", draft_update={"summary": "קיים"},
    )

    result = IntroInterview(_FakeLlm(response)).next_turn([], draft)

    assert any("לא נשמרה" in line for line in result["open_points"])


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
