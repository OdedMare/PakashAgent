"""The workspace HTTP boundary: cookies, guards, and tenant isolation.

The isolation tests are the point of the feature. They assert the thing a
reviewer would otherwise have to take on trust -- that one workspace cannot
read or write another's interview even when it knows the session id.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies import Guards
from app.api.routers import interview, workspace
from app.bl.interview_service import InterviewService
from app.bl.workspace_service import WorkspaceService
from app.common.errors import AppError
from app.common.sessions import COOKIE_NAME, ROLE_BOSS, ROLE_MEMBER, issue

from tests.test_interview_api import _FakeRepository, _ScriptedLlm, _question
from tests.test_workspace import _FakeTeams

SECRET = "test-secret"


class _FakeRepo(_FakeRepository, _FakeTeams):
    """Both halves, composed exactly as the real `Repository` composes them."""

    def __init__(self):
        _FakeRepository.__init__(self)
        _FakeTeams.__init__(self)


@pytest.fixture
def app_and_repo():
    repository = _FakeRepo()
    guards = Guards(SECRET)
    app = FastAPI()
    app.include_router(workspace.build_router(
        WorkspaceService(repository), guards, SECRET, 30
    ))
    app.include_router(interview.build_router(
        InterviewService(repository, _ScriptedLlm([_question()])), guards
    ))

    @app.exception_handler(AppError)
    async def handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc)}
        )

    return app, repository


@pytest.fixture
def client(app_and_repo):
    return TestClient(app_and_repo[0])


def _make_team(client, name="צוות", password="sod-gadol"):
    response = client.post(
        "/api/workspace", json={"name": name, "password": password}
    )
    assert response.status_code == 200
    return response.json()


# --- cookies ----------------------------------------------------------------

def test_creating_a_workspace_sets_an_httponly_session_cookie(client):
    response = client.post(
        "/api/workspace", json={"name": "צוות", "password": "sod-gadol"}
    )

    cookie = response.headers["set-cookie"]
    assert COOKIE_NAME in cookie
    # HttpOnly keeps the session out of reach of any script on the page, so
    # an XSS bug cannot read it out and replay it.
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie.replace("Lax", "lax")


def test_the_raw_password_never_appears_in_the_response(client):
    body = client.post(
        "/api/workspace", json={"name": "צוות", "password": "sod-gadol"}
    ).text

    assert "sod-gadol" not in body


def test_logging_out_clears_the_cookie(client):
    _make_team(client)

    response = client.post("/api/workspace/logout")

    assert response.status_code == 200
    assert client.get("/api/workspace/me").status_code == 401


def test_a_short_password_is_a_422_from_the_contract(client):
    response = client.post(
        "/api/workspace", json={"name": "צוות", "password": "12"}
    )

    assert response.status_code == 422


# --- the guard --------------------------------------------------------------

def test_an_anonymous_visitor_cannot_reach_the_interview(client):
    assert client.post("/api/interview").status_code == 401
    assert client.get("/api/workspace/me").status_code == 401


def test_a_forged_cookie_cannot_reach_the_interview(client):
    client.cookies.set(COOKIE_NAME, issue("wrong-secret", "team-1", ROLE_BOSS, 30))

    assert client.post("/api/interview").status_code == 401


def test_a_member_cannot_start_or_answer_an_interview(client):
    """D5 at the routing layer: the member area is a view, not a second
    editing surface, so no member session reaches an authoring route."""
    team = _make_team(client)
    client.cookies.set(COOKIE_NAME, issue(SECRET, team["id"], ROLE_MEMBER, 30))

    started = client.post("/api/interview")

    assert started.status_code == 401
    assert "מנהל" in started.json()["detail"]


def test_a_member_cannot_rotate_the_share_link(client):
    team = _make_team(client)
    client.cookies.set(COOKIE_NAME, issue(SECRET, team["id"], ROLE_MEMBER, 30))

    assert client.post("/api/workspace/member-link/rotate").status_code == 401


def test_a_member_sees_the_workspace_but_not_its_share_token(client):
    team = _make_team(client)
    client.cookies.set(COOKIE_NAME, issue(SECRET, team["id"], ROLE_MEMBER, 30))

    body = client.get("/api/workspace/me").json()

    assert body["name"] == "צוות"
    assert body["role"] == ROLE_MEMBER
    assert body["member_token"] is None


def test_the_boss_sees_the_share_token(client):
    _make_team(client)

    body = client.get("/api/workspace/me").json()

    assert body["role"] == ROLE_BOSS
    assert body["member_token"]


# --- the share link ---------------------------------------------------------

def test_a_share_link_grants_a_member_session(client):
    team = _make_team(client)
    client.post("/api/workspace/logout")

    response = client.post("/api/workspace/member/%s" % team["member_token"])

    assert response.status_code == 200
    assert response.json()["role"] == ROLE_MEMBER
    assert client.get("/api/workspace/me").json()["role"] == ROLE_MEMBER


def test_an_invalid_share_link_is_a_401(client):
    assert client.post("/api/workspace/member/nope").status_code == 401


def test_the_team_list_is_public_and_carries_no_secrets(client):
    _make_team(client, name="צוות א")
    client.post("/api/workspace/logout")

    listed = client.get("/api/workspace/teams").json()

    assert listed[0]["name"] == "צוות א"
    assert "member_token" not in listed[0]
    assert "password_hash" not in listed[0]


# --- tenant isolation -------------------------------------------------------

def test_one_workspace_cannot_read_another_s_interview(app_and_repo):
    """The headline guarantee. Knowing the session id is not enough --
    the row is filtered by the team in the cookie."""
    app, _ = app_and_repo
    boss_a = TestClient(app)
    boss_b = TestClient(app)
    _make_team(boss_a, name="צוות א", password="sod-alef")
    _make_team(boss_b, name="צוות ב", password="sod-bet")

    session_id = boss_a.post("/api/interview").json()["session_id"]

    assert boss_a.get("/api/interview/%s" % session_id).status_code == 200
    assert boss_b.get("/api/interview/%s" % session_id).status_code == 404


def test_one_workspace_cannot_answer_another_s_interview(app_and_repo):
    app, _ = app_and_repo
    boss_a = TestClient(app)
    boss_b = TestClient(app)
    _make_team(boss_a, name="צוות א", password="sod-alef")
    _make_team(boss_b, name="צוות ב", password="sod-bet")
    session_id = boss_a.post("/api/interview").json()["session_id"]

    response = boss_b.post(
        "/api/interview/%s/answer" % session_id, json={"content": "כן"}
    )

    assert response.status_code == 404


def test_each_workspace_gets_its_own_interview(app_and_repo):
    app, _ = app_and_repo
    boss_a = TestClient(app)
    boss_b = TestClient(app)
    _make_team(boss_a, name="צוות א", password="sod-alef")
    _make_team(boss_b, name="צוות ב", password="sod-bet")

    first = boss_a.post("/api/interview").json()["session_id"]
    second = boss_b.post("/api/interview").json()["session_id"]

    assert first != second


def test_a_second_device_continues_the_same_interview(app_and_repo):
    """The interview belongs to the workspace, not to the browser that began
    it -- otherwise logging in on a phone silently starts a parallel one."""
    app, _ = app_and_repo
    laptop = TestClient(app)
    team = _make_team(laptop, name="צוות א", password="sod-alef")
    started = laptop.post("/api/interview").json()["session_id"]

    phone = TestClient(app)
    phone.post(
        "/api/workspace/login",
        json={"team_id": team["id"], "password": "sod-alef"},
    )
    resumed = phone.post("/api/interview").json()["session_id"]

    assert resumed == started
