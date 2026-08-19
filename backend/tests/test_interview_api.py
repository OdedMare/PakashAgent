"""The interview HTTP contract and its persistence, over a fake model.

The repository is faked rather than mocked against Postgres: what these
assert is that a turn is *remembered* — a real database would test psycopg,
not the contract.
"""

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
