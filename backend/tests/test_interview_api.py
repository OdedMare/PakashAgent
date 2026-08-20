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
from app.bl.interview import empty_draft
from app.bl.interview_service import InterviewService
from app.common.errors import AppError, ConflictError, NotFoundError
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

    def latest_session(self, team_id):
        found = [
            session for session in self.sessions.values()
            if session["team_id"] == team_id
        ]
        if not found:
            return None
        return self.get_session(found[-1]["id"], team_id)

    def reopen(self, session_id, team_id, pending):
        # The profile is deliberately left where it is: the management area
        # goes on reading it while the interview is open again.
        self.sessions[session_id].update(status="active", pending=pending)
        return self.get_session(session_id, team_id)

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
            return self.responses.pop(0)
        return self.responses[0]


def _question(question="על מה המשמרת אחראית?", **overrides):
    response = {
        "reply": "תודה, רשמתי.",
        "question": {
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
        "draft": _empty(),
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
        reply="זה מה שסיכמנו. נכון?", draft=_profile(),
    )


def _complete():
    """The turn after the manager confirms."""
    return _question(
        question=None, awaiting_confirmation=False, ready=True,
        reply="מצוין, סיימנו.", draft=_profile(),
    )


def _client(llm, role=ROLE_BOSS, team=TEAM):
    """A client already holding a session cookie for `team`.

    Authenticated by default: every test here predates workspaces and asserts
    on interview behaviour, not on the guard. The guard gets its own tests
    below, which pass a member role or no cookie at all.
    """
    repository = _FakeRepository()
    service = InterviewService(repository, llm)
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


def test_the_question_is_persisted_as_an_assistant_turn():
    client, repository = _client(_ScriptedLlm([_question()]))

    session_id = client.post("/api/interview").json()["session_id"]

    turns = repository.history(session_id)
    assert [row["role"] for row in turns] == ["assistant"]
    payload = turns[0]["payload"]
    assert payload["question"]["options"][1]["label"] == "רציפות תפעולית"
    assert payload["draft"] is not None


def test_an_answer_is_recorded_and_passed_back_to_the_model():
    llm = _ScriptedLlm([_question(), _question("איך יודעים?")])
    client, repository = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]

    body = client.post(
        "/api/interview/%s/answer" % session_id,
        json={"content": "רציפות תפעולית"},
    ).json()

    assert body["question"]["question"] == "איך יודעים?"
    assert [row["role"] for row in repository.history(session_id)] == [
        "assistant", "user", "assistant"
    ]
    assert "רציפות תפעולית" in llm.calls[-1]


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
        _ScriptedLlm([_question(), _confirming(), _complete()])
    )
    session_id = client.post("/api/interview").json()["session_id"]

    # The summary turn presents the profile for approval but does not store
    # it: `ready` is false until the manager actually confirms.
    summary = client.post(
        "/api/interview/%s/answer" % session_id, json={"content": "זהו"}
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
    client, _ = _client(_ScriptedLlm([_question(), _complete()]))
    session_id = client.post("/api/interview").json()["session_id"]
    client.post(
        "/api/interview/%s/answer" % session_id, json={"content": "כן"}
    )

    response = client.post(
        "/api/interview/%s/answer" % session_id, json={"content": "עוד משהו"}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "הראיון כבר הושלם"


def test_resuming_a_completed_interview_returns_the_profile():
    client, _ = _client(_ScriptedLlm([_question(), _complete()]))
    session_id = client.post("/api/interview").json()["session_id"]
    client.post("/api/interview/%s/answer" % session_id, json={"content": "כן"})

    body = client.get("/api/interview/%s" % session_id).json()

    assert body["status"] == "complete"
    assert body["profile"]["summary"] == "צוות תפעול, שלוש משמרות"


@pytest.mark.parametrize("content", ["", "   "])
def test_an_empty_answer_is_rejected(content):
    client, _ = _client(_ScriptedLlm([_question()]))
    session_id = client.post("/api/interview").json()["session_id"]

    response = client.post(
        "/api/interview/%s/answer" % session_id, json={"content": content}
    )

    assert response.status_code in (400, 422, 502)


def test_an_unknown_session_is_a_404():
    client, _ = _client(_ScriptedLlm([_question()]))

    assert client.get("/api/interview/nope").status_code == 404


def test_health_reports_ok():
    client, _ = _client(_ScriptedLlm([_question()]))

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/health/database").json() == {"database": "ok"}


# -- ending early, and coming back to add more ------------------------------
#
# Two doors out of the topic list: `finish` writes the profile from what has
# been said so far, and `continue` reopens the same conversation to add to
# it. What guards the first is `scheduling_gaps` — a profile a schedule
# cannot be built from is not finished, it is a session that now asks about
# exactly what is missing.


def _schedulable():
    """The profile of a workplace that can actually be scheduled."""
    return dict(_profile(), shifts=[
        {"name": "בוקר", "start_time": "08:00", "end_time": "16:00"},
    ])


def _gathered(draft):
    """A turn that has settled `draft` and is still asking questions."""
    return _question("ומי עוד עובד?", draft=draft)


def test_finishing_early_stores_what_was_gathered_without_another_model_call():
    llm = _ScriptedLlm([_gathered(_schedulable())])
    client, repository = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]
    calls_before = len(llm.calls)

    body = client.post("/api/interview/%s/finish" % session_id).json()

    assert body["status"] == "complete"
    assert body["profile"]["workplace"]["name"] == "צוות תפעול"
    assert body["gaps"] == []
    assert repository.sessions[session_id]["status"] == "complete"
    # Nothing to generate: the draft is already the answer, and a closing
    # turn from the model could only restate it — or decide to keep asking.
    assert len(llm.calls) == calls_before


def test_finishing_early_leaves_the_decision_in_the_thread():
    client, repository = _client(_ScriptedLlm([_gathered(_schedulable())]))
    session_id = client.post("/api/interview").json()["session_id"]

    client.post("/api/interview/%s/finish" % session_id)

    turns = repository.history(session_id)
    assert [row["role"] for row in turns] == ["assistant", "user", "assistant"]
    # The manager's own sentence, so the conversation still reads as one
    # thing if it is ever reopened.
    assert "לסיים" in turns[1]["content"]
    assert turns[2]["content"]


def test_finishing_with_nothing_gathered_asks_for_the_gaps_instead():
    llm = _ScriptedLlm([_question(), _question("אילו משמרות יש?")])
    client, repository = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]

    body = client.post("/api/interview/%s/finish" % session_id).json()

    assert body["status"] == "question"
    assert body["question"]["question"] == "אילו משמרות יש?"
    assert len(body["gaps"]) == 2
    # Not completed, and no profile written from a draft nothing can be
    # built out of.
    assert repository.sessions[session_id]["status"] == "active"
    assert repository.sessions[session_id]["profile"] is None


def test_the_gaps_are_the_only_thing_the_closing_turn_asks_about():
    llm = _ScriptedLlm([_question(), _question("אילו משמרות יש?")])
    client, _ = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]

    client.post("/api/interview/%s/finish" % session_id)

    payload = json.loads(llm.calls[-1])
    assert len(payload["closing_gaps"]) == 2
    assert any("משמרת" in line for line in payload["closing_gaps"])


def test_a_turn_carries_what_still_blocks_a_schedule():
    client, _ = _client(_ScriptedLlm([_question()]))

    body = client.post("/api/interview").json()

    assert len(body["gaps"]) == 2


def test_finishing_an_already_finished_interview_serves_the_profile():
    client, _ = _client(_ScriptedLlm([_question(), _complete()]))
    session_id = client.post("/api/interview").json()["session_id"]
    client.post("/api/interview/%s/answer" % session_id, json={"content": "כן"})

    body = client.post("/api/interview/%s/finish" % session_id)

    assert body.status_code == 200
    assert body.json()["status"] == "complete"


def test_continuing_reopens_the_finished_interview_with_its_history():
    llm = _ScriptedLlm([_gathered(_schedulable())])
    client, repository = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]
    client.post("/api/interview/%s/finish" % session_id)

    body = client.post("/api/interview/continue").json()

    assert body["session_id"] == session_id
    assert body["status"] == "question"
    assert repository.sessions[session_id]["status"] == "active"
    # The whole conversation is still there — the agent knows everything
    # already settled, so the manager answers only what is new.
    assert len(body["turns"]) > 3
    assert "להשלים" in body["turns"][-2]["content"]


def test_continuing_hands_the_agreed_profile_back_as_the_draft():
    llm = _ScriptedLlm([_gathered(_schedulable())])
    client, _ = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]
    client.post("/api/interview/%s/finish" % session_id)

    client.post("/api/interview/continue")

    payload = json.loads(llm.calls[-1])
    assert payload["draft_so_far"]["workplace"]["name"] == "צוות תפעול"


def test_continuing_keeps_the_profile_readable_while_the_interview_is_open():
    llm = _ScriptedLlm([_gathered(_schedulable())])
    client, repository = _client(llm)
    session_id = client.post("/api/interview").json()["session_id"]
    client.post("/api/interview/%s/finish" % session_id)

    client.post("/api/interview/continue")

    # Adding one fact to a workplace must not take its schedule away for as
    # long as the manager is answering.
    assert repository.sessions[session_id]["profile"] is not None


def test_continuing_an_open_interview_resumes_it_without_a_model_call():
    llm = _ScriptedLlm([_question()])
    client, _ = _client(llm)
    client.post("/api/interview")
    calls_before = len(llm.calls)

    body = client.post("/api/interview/continue").json()

    assert body["status"] == "question"
    assert len(llm.calls) == calls_before


def test_continuing_with_no_interview_at_all_starts_one():
    client, _ = _client(_ScriptedLlm([_question()]))

    body = client.post("/api/interview/continue").json()

    assert body["status"] == "question"
    assert body["session_id"]


def test_a_member_can_neither_end_nor_reopen_the_boss_s_interview():
    client, _ = _client(_ScriptedLlm([_question()]), role=ROLE_BOSS)
    session_id = client.post("/api/interview").json()["session_id"]
    client.cookies.set(COOKIE_NAME, issue(SECRET, TEAM, ROLE_MEMBER, 1))

    # The interview is authoring, and D5 keeps employees on the reading side
    # of the product — the two new doors are guarded exactly like the rest.
    assert client.post(
        "/api/interview/%s/finish" % session_id
    ).status_code == 401
    assert client.post("/api/interview/continue").status_code == 401
