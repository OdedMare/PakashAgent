"""The interview HTTP contract and its persistence, over a fake model.

The repository is faked rather than mocked against Postgres: what these
assert is that a turn is *remembered* — a real database would test psycopg,
not the contract.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import Guards
from app.api.routers import health, interview
from app.bl.interview import (
    FINISH_ANSWER, INTERVIEW_TOPICS, empty_draft,
)
from app.bl.interview_service import InterviewService
from app.common.errors import AgentError, AppError, ConflictError, NotFoundError
from app.common.sessions import COOKIE_NAME, ROLE_BOSS, ROLE_MEMBER, issue

# The team every test authenticates into. Its value is arbitrary; what matters
# is that the routes now take it from the cookie rather than the request.
TEAM = "team-under-test"
SECRET = "test-secret"


class _FakeRepository:
    def __init__(self):
        self.sessions = {}
        self.turns = {}
        self._next = 0

    def _new_id(self):
        self._next += 1
        return "session-%d" % self._next

    def create_session(self, team_id):
        session_id = self._new_id()
        self.sessions[session_id] = {
            "id": session_id, "team_id": team_id, "status": "active",
            "profile": None, "pending": None,
        }
        self.turns[session_id] = []
        return self.get_session(session_id, team_id)

    def get_session(self, session_id, team_id):
        session = self.sessions.get(session_id)
        # A session belonging to another team is indistinguishable from one
        # that does not exist — the real repository filters in SQL and gets
        # the same 404, and the tests below depend on that being true.
        if session is None or session["team_id"] != team_id:
            raise NotFoundError("הפריט לא נמצא")
        session = dict(session)
        session["turns"] = self.history(session_id)
        return session

    def active_session(self, team_id):
        for session in self.sessions.values():
            if session["team_id"] == team_id and session["status"] == "active":
                return self.get_session(session["id"], team_id)
        return None

    def history(self, session_id):
        return [dict(row) for row in self.turns.get(session_id, [])]

    def append_turn(self, session_id, role, content, payload=None):
        self.turns[session_id].append(
            {"role": role, "content": content, "payload": payload}
        )

    def save_pending(self, session_id, pending):
        self.sessions[session_id]["pending"] = pending

    def complete(self, session_id, team_id, profile):
        if self.sessions[session_id]["status"] == "complete":
            raise ConflictError("הראיון כבר הושלם")
        self.sessions[session_id].update(
            status="complete", profile=profile, pending=None
        )
        return self.get_session(session_id, team_id)

    def health(self):
        return {"database": "ok"}


class _ScriptedLlm:
    """Returns each queued response in turn, repeating the last one."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete_json(self, system, user, schema=None, flow=""):
        self.calls.append(user)
        if len(self.responses) > 1:
            response = self.responses.pop(0)
        else:
            response = self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def _question(question="על מה המשמרת אחראית?", **overrides):
    response = {
        "reply": "תודה, רשמתי.",
        "question": {
            "topic_id": "workplace_and_cycle",
            "question": question,
            "recommendation": "כדאי לתאר את האחריות במשפט אחד.",
            "why": "בלי זה אי אפשר לדעת מה נחשב משמרת מוצלחת.",
            "options": [
                {"label": "מתן שירות", "answer": "אנחנו נותנים שירות ומענה."},
                {
                    "label": "רציפות תפעולית",
                    "answer": "אנחנו אחראים על רציפות תפעולית.",
                },
            ],
        },
        "resolved": [],
        "open_points": ["עדיין לא הוגדרו סוגי המשמרות."],
        "awaiting_confirmation": False,
        "ready": False,
        "draft_update": {},
    }
    response.update(overrides)
    return response


def _empty():
    return dict(empty_draft())


def _profile():
    return dict(_empty(), **{
        "workplace": {
            "name": "צוות תפעול", "mission": "רציפות",
            "success_criteria": ["שירות רציף"], "timezone": "Asia/Jerusalem",
            "operating_days": ["א-ה"], "planning_horizon": "שבועיים",
            "scheduler_name": "שרון", "scheduler_works_shifts": False,
        },
        "employees": [{"name": "דנה", "role": "נציגה"}],
        "shifts": [{"name": "בוקר", "start_time": "08:00"}],
        "dependencies": [], "rules": [],
        "availability_process": "שרון מזין", "constraint_deadline": "שבוע",
        "casual_worker_policy": "לפי צורך",
        "training_policy": {
            "shadow_shift_fraction": 0.5, "shadow_shifts_per_week": 5,
            "alternate_halves": True, "counts_toward_staffing": False,
        },
        "rest_policy": "8 שעות", "weekend_policy": "שישי-שבת",
        "fairness_policy": "איזון", "conflict_policy": "מציגים לשרון",
        "existing_schedule_source": "קבצים קודמים",
        "summary": "צוות תפעול, שלוש משמרות",
    })


def _confirming():
    """The turn that presents the summary. Not yet ready — the manager has
    not confirmed it."""
    return _question(
        question=None, awaiting_confirmation=True, ready=False,
        reply="זה מה שסיכמנו. נכון?", draft_update=_profile(),
    )


def _complete():
    """The turn after the manager confirms."""
    return _question(
        question=None, awaiting_confirmation=False, ready=True,
        reply="מצוין, סיימנו.", draft_update=_profile(),
    )


def _completion_responses():
    responses = []
    for topic in INTERVIEW_TOPICS:
        response = _question(topic["question"])
        response["question"]["topic_id"] = topic["id"]
        responses.append(response)
    return responses + [_confirming(), _complete()]


def _answer_required_questions(client, session_id):
    body = None
    for _ in INTERVIEW_TOPICS:
        body = client.post(
            "/api/interview/%s/answer" % session_id,
            json={"content": "תשובת חובה"},
        ).json()
    return body


def _client(llm, role=ROLE_BOSS, team=TEAM, launch=None):
    """A client already holding a session cookie for `team`.

    Authenticated by default: every test here predates workspaces and asserts
    on interview behaviour, not on the guard. The guard gets its own tests
    below, which pass a member role or no cookie at all.
    """
    repository = _FakeRepository()
    service = InterviewService(repository, llm, launch=launch or (
        lambda target, *args: target(*args)
    ))
    app = FastAPI()
    app.include_router(health.build_router(repository))
    app.include_router(interview.build_router(service, Guards(SECRET)))

    @app.exception_handler(AppError)
    async def handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc)}
        )

    client = TestClient(app)
    if role is not None:
        client.cookies.set(COOKIE_NAME, issue(SECRET, team, role, 1))
    return client, repository


class _DeferredLauncher:
    def __init__(self):
        self.jobs = []

    def __call__(self, target, *args):
        self.jobs.append((target, args))

    def run_next(self):
        target, args = self.jobs.pop(0)
        target(*args)


def test_interview_generation_is_polled_instead_of_blocking_the_post():
    launcher = _DeferredLauncher()
    llm = _ScriptedLlm([_question()])
    client, _ = _client(llm, launch=launcher)

    queued = client.post("/api/interview").json()

    assert queued["status"] == "processing"
    assert llm.calls == []

    launcher.run_next()
    completed = client.get("/api/interview/%s" % queued["session_id"]).json()

    assert completed["status"] == "question"
    assert completed["question"]["question"] == "על מה המשמרת אחראית?"


def test_retry_does_not_record_the_same_answer_twice():
    launcher = _DeferredLauncher()
    llm = _ScriptedLlm([
        _question(), AgentError("המודל לא זמין"), _question("איך יודעים?"),
    ])
    client, repository = _client(llm, launch=launcher)

    started = client.post("/api/interview").json()
    launcher.run_next()
    session_id = started["session_id"]
    client.post(
        "/api/interview/%s/answer" % session_id,
        json={"content": "רציפות תפעולית"},
    )
    launcher.run_next()

    failed = client.get("/api/interview/%s" % session_id).json()
    assert failed["status"] == "error"

    queued = client.post("/api/interview/%s/retry" % session_id).json()
    assert queued["status"] == "processing"
    launcher.run_next()

    completed = client.get("/api/interview/%s" % session_id).json()
    assert completed["status"] == "question"
    assert [row["role"] for row in repository.history(session_id)].count(
        "user"
    ) == 1


def test_starting_an_interview_returns_the_first_question_with_options():
    client, _ = _client(_ScriptedLlm([_question()]))

    body = client.post("/api/interview").json()

    assert body["status"] == "question"
    assert body["question"]["question"] == "על מה המשמרת אחראית?"
    assert body["question"]["recommendation"]
    assert [option["label"] for option in body["question"]["options"]] == [
        "מתן שירות", "רציפות תפעולית"
    ]
    # The draft rides along from the very first turn, so the summary panel
    # fills in as the interview runs rather than appearing at the end.
    assert body["draft"] is not None
    assert body["session_id"]


def test_starting_from_an_import_seeds_a_draft_for_the_first_question():
    llm = _ScriptedLlm([_question(draft_update={})])
    client, _ = _client(llm)

    body = client.post("/api/interview", json={
        "workplace_name": "מוקד צפון",
        "source_files": ["july.xlsx"],
        "employees": {"דנה": ["בוקר"], "רון": ["ערב"]},
        "shifts": {"בוקר": ["ראשון", "שני"], "ערב": ["שני"]},
        "starts_on": "2026-07-01",
        "ends_on": "2026-07-31",
    }).json()

    assert body["draft"]["workplace"]["name"] == "מוקד צפון"
    assert [row["name"] for row in body["draft"]["employees"]] == [
        "דנה", "רון",
    ]
    assert body["draft"]["shifts"][0]["days"] == ["ראשון", "שני"]
    payload = json.loads(llm.calls[0])
    assert payload["draft_so_far"]["existing_schedule_source"].startswith(
        "קבצי סידור קיימים: july.xlsx"
    )


def test_a_correction_does_not_count_as_answering_the_pending_topic():
    second = _question(INTERVIEW_TOPICS[1]["question"])
    second["question"]["topic_id"] = INTERVIEW_TOPICS[1]["id"]
    client, repository = _client(_ScriptedLlm([_question(), second, second]))
    session_id = client.post("/api/interview").json()["session_id"]

    corrected = client.post(
        "/api/interview/%s/answer" % session_id,
        json={"content": "תיקון: השם הוא מוקד צפון", "mode": "correction"},
    ).json()
    assert corrected["question"]["topic_id"] == INTERVIEW_TOPICS[0]["id"]

    answered = client.post(
        "/api/interview/%s/answer" % session_id,
        json={"content": "מוקד צפון, סידור לשבוע"},
    ).json()
    assert answered["question"]["topic_id"] == INTERVIEW_TOPICS[1]["id"]
    correction = repository.history(session_id)[1]
    assert correction["payload"] == {"mode": "correction"}


def test_the_question_is_persisted_as_an_assistant_turn():
    client, repository = _client(_ScriptedLlm([_question()]))

    session_id = client.post("/api/interview").json()["session_id"]

    turns = repository.history(session_id)
    assert [row["role"] for row in turns] == ["assistant"]
    payload = turns[0]["payload"]
    assert payload["question"]["options"][1]["label"] == "רציפות תפעולית"
    assert payload["draft"] is not None


def test_token_usage_is_persisted_with_the_assistant_turn():
    client, repository = _client(_ScriptedLlm([
        _question(_usage={"prompt_tokens": 100, "completion_tokens": 20}),
    ]))

    session_id = client.post("/api/interview").json()["session_id"]

    assert repository.history(session_id)[0]["payload"]["_usage"] == {
        "prompt_tokens": 100, "completion_tokens": 20,
    }


def test_an_answer_is_recorded_and_passed_back_to_the_model():
    llm = _ScriptedLlm([_question(), _question("איך יודעים?")])
    client, repository = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]

    body = client.post(
        "/api/interview/%s/answer" % session_id,
        json={"content": "רציפות תפעולית"},
    ).json()

    assert body["question"]["question"] == INTERVIEW_TOPICS[1]["question"]
    assert [row["role"] for row in repository.history(session_id)] == [
        "assistant", "user", "assistant"
    ]
    assert "רציפות תפעולית" in llm.calls[-1]
    payload = json.loads(llm.calls[-1])
    assert payload["questions_already_asked"] == [
        "על מה המשמרת אחראית?"
    ]
    assert "על מה המשמרת אחראית?" in payload["recent_conversation"][0]["content"]


def test_resuming_replays_the_pending_question_without_calling_the_model():
    llm = _ScriptedLlm([_question()])
    client, _ = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]
    calls_after_start = len(llm.calls)

    body = client.get("/api/interview/%s" % session_id).json()

    assert body["question"]["question"] == "על מה המשמרת אחראית?"
    assert len(llm.calls) == calls_after_start


def test_a_confirmed_summary_completes_the_session_and_stores_the_profile():
    client, repository = _client(
        _ScriptedLlm(_completion_responses())
    )
    session_id = client.post("/api/interview").json()["session_id"]

    consent = _answer_required_questions(client, session_id)
    assert consent["question"]["question"].startswith(
        "סיימנו את שאלות החובה"
    )

    # The summary turn presents the profile for approval but does not store
    # it: `ready` is false until the manager actually confirms.
    summary = client.post(
        "/api/interview/%s/answer" % session_id,
        json={"content": FINISH_ANSWER},
    ).json()
    assert summary["status"] == "question"
    assert summary["awaiting_confirmation"] is True
    assert repository.sessions[session_id]["status"] == "active"

    body = client.post(
        "/api/interview/%s/answer" % session_id, json={"content": "כן, נכון"}
    ).json()

    assert body["status"] == "complete"
    assert body["profile"]["workplace"]["name"] == "צוות תפעול"
    assert body["question"] is None
    assert repository.sessions[session_id]["status"] == "complete"


def test_answering_a_completed_interview_is_rejected():
    client, _ = _client(_ScriptedLlm(_completion_responses()))
    session_id = client.post("/api/interview").json()["session_id"]
    _answer_required_questions(client, session_id)
    client.post(
        "/api/interview/%s/answer" % session_id,
        json={"content": FINISH_ANSWER},
    )
    client.post(
        "/api/interview/%s/answer" % session_id, json={"content": "כן"}
    )

    response = client.post(
        "/api/interview/%s/answer" % session_id, json={"content": "עוד משהו"}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "הראיון כבר הושלם"


def test_resuming_a_completed_interview_returns_the_profile():
    client, _ = _client(_ScriptedLlm(_completion_responses()))
    session_id = client.post("/api/interview").json()["session_id"]
    _answer_required_questions(client, session_id)
    client.post(
        "/api/interview/%s/answer" % session_id,
        json={"content": FINISH_ANSWER},
    )
    client.post("/api/interview/%s/answer" % session_id, json={"content": "כן"})

    body = client.get("/api/interview/%s" % session_id).json()

    assert body["status"] == "complete"
    assert body["profile"]["summary"] == "צוות תפעול, שלוש משמרות"


def test_a_turn_with_no_prose_does_not_wedge_the_interview():
    """A model turn whose `reply` is empty must still be answerable.

    The empty reply is stored as a thread row and replayed on every later
    turn, so a history validator that rejected it would fail identically
    forever — the interview would be unanswerable from the second question
    on, with no way for the manager to recover it.
    """
    llm = _ScriptedLlm([_question(reply=""), _question(reply="")])
    client, _ = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]

    first = client.post(
        "/api/interview/%s/answer" % session_id, json={"content": "מענה"}
    )
    second = client.post(
        "/api/interview/%s/answer" % session_id, json={"content": "עוד מענה"}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    # The turn is kept, standing under the question it asked rather than
    # rendering as a blank row in the thread.
    assert all(
        message["content"] for message in second.json()["turns"]
    )


def test_a_blank_stored_turn_is_replayed_from_its_question():
    """A row written blank before the fix still reaches the model.

    Such a row carries its question in the payload, so the turn is recovered
    from there rather than replayed empty — dropping it would take the
    question with it and the model would re-ask something already answered.
    """
    llm = _ScriptedLlm([_question()])
    client, repository = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]
    # A row exactly as the old code stored it: no content, question in payload.
    repository.turns[session_id][0]["content"] = ""

    client.post("/api/interview/%s/answer" % session_id, json={"content": "מענה"})

    replayed = json.loads(llm.calls[-1])["recent_conversation"]
    assert replayed[0] == {
        "role": "assistant", "content": "על מה המשמרת אחראית?"
    }


@pytest.mark.parametrize("content", ["", "   "])
def test_an_empty_answer_is_rejected(content):
    client, _ = _client(_ScriptedLlm([_question()]))
    session_id = client.post("/api/interview").json()["session_id"]

    response = client.post(
        "/api/interview/%s/answer" % session_id, json={"content": content}
    )

    assert response.status_code in (400, 422, 502)


# -- ending the interview early --------------------------------------------


def test_ending_stores_the_draft_so_far_as_the_profile():
    """The manager's escape hatch: close now, keep what was collected."""
    partial = dict(_empty(), **{
        "workplace": {"name": "צוות תפעול", "mission": "רציפות"},
        "shifts": [{"name": "בוקר", "start_time": "08:00"}],
    })
    client, repository = _client(
        _ScriptedLlm([_question(draft_update=partial)])
    )
    session_id = client.post("/api/interview").json()["session_id"]

    body = client.post("/api/interview/%s/end" % session_id).json()

    assert body["status"] == "complete"
    stored = repository.sessions[session_id]
    assert stored["status"] == "complete"
    assert stored["profile"]["workplace"]["name"] == "צוות תפעול"
    assert stored["profile"]["shifts"][0]["name"] == "בוקר"


def test_ending_costs_no_model_call():
    """The escape hatch from a slow model must not need that model."""
    llm = _ScriptedLlm([_question()])
    client, _ = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]
    before = len(llm.calls)

    client.post("/api/interview/%s/end" % session_id)

    assert len(llm.calls) == before


def test_ending_records_what_the_profile_still_owes():
    """The gaps travel with the profile — `bl/tools.py` reads them back."""
    client, repository = _client(_ScriptedLlm([_question()]))
    session_id = client.post("/api/interview").json()["session_id"]

    client.post("/api/interview/%s/end" % session_id)

    completeness = repository.sessions[session_id]["profile"]["completeness"]
    assert completeness["complete"] is False
    # The first turn's draft is empty, so every required topic is owed.
    assert any("משמרת" in line for line in completeness["missing_topics"])


def test_a_confirmed_interview_records_no_completeness_block():
    """Absence is what marks a profile finished; nothing is backfilled."""
    client, repository = _client(
        _ScriptedLlm(_completion_responses())
    )
    session_id = client.post("/api/interview").json()["session_id"]
    _answer_required_questions(client, session_id)
    client.post(
        "/api/interview/%s/answer" % session_id,
        json={"content": FINISH_ANSWER},
    )
    client.post(
        "/api/interview/%s/answer" % session_id, json={"content": "כן"}
    )

    profile = repository.sessions[session_id]["profile"]
    assert profile is not None
    assert "completeness" not in profile


def test_ending_twice_serves_the_same_finished_interview():
    """A double-clicked button ends the same interview, not a conflict."""
    client, _ = _client(_ScriptedLlm([_question()]))
    session_id = client.post("/api/interview").json()["session_id"]

    first = client.post("/api/interview/%s/end" % session_id)
    second = client.post("/api/interview/%s/end" % session_id)

    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["status"] == "complete"


def test_a_member_cannot_end_an_interview():
    """Ending writes the profile, which is authoring (D5/D10).

    Refused by the guard before the session id is ever looked at, which is
    why an id that does not exist still answers 401 rather than 404.
    """
    client, _ = _client(_ScriptedLlm([_question()]), role=ROLE_MEMBER)

    assert client.post("/api/interview/whatever/end").status_code == 401


def test_an_unknown_session_is_a_404():
    client, _ = _client(_ScriptedLlm([_question()]))

    assert client.get("/api/interview/nope").status_code == 404


def test_health_reports_ok():
    client, _ = _client(_ScriptedLlm([_question()]))

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/health/database").json() == {"database": "ok"}
