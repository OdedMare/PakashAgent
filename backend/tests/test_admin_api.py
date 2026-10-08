"""The צוות משמרות זהב operator console (D28).

What these pin down is the access story: that the console has its own door,
that neither kind of cookie opens the other's routes, that a suspended or
deleted team stops working under cookies already issued, and that deleting
needs the team's name typed back.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies.dependencies import Guards
from app.api.routers import admin, settings as settings_router, workspace
from app.bl.admin_service import AdminService
from app.bl.workspace_service.service import WorkspaceService
from app.common.errors.errors import AppError, NotFoundError
from app.common.sessions.sessions import (
    ADMIN_COOKIE_NAME, COOKIE_NAME, ROLE_ADMIN, issue, issue_admin, read,
    read_admin,
)

from tests.test_workspace import _FakeTeams

SECRET = "test-secret"
PASSWORD = "010802"


class _FakeAdminRepo(_FakeTeams):
    """The team half plus the operator's cross-team reads, in memory."""

    def admin_team(self, team_id):
        if team_id not in self.teams:
            raise NotFoundError("הצוות לא נמצא")
        team = dict(self.teams[team_id])
        team.pop("password_hash")
        return team

    def admin_teams(self):
        return [self.admin_team(team_id) for team_id in self.teams]

    def admin_totals(self):
        return {"teams": len(self.teams)}

    def update_team_admin(self, team_id, fields):
        if team_id not in self.teams:
            raise NotFoundError("הצוות לא נמצא")
        self.teams[team_id].update(fields)

    def delete_team(self, team_id):
        self.teams.pop(team_id)

    def team_is_active(self, team_id):
        team = self.teams.get(team_id)
        return bool(team and team.get("active", True))

    def release_identity(self, team_id, employee):
        return None


class _FakeStore:
    def public(self):
        return {"llm_model": "gemma3:27b", "openai_api_key": "********"}


@pytest.fixture
def world():
    repository = _FakeAdminRepo()
    guards = Guards(SECRET, team_active=repository.team_is_active)
    service = WorkspaceService(repository)
    app = FastAPI()
    app.include_router(workspace.build_router(service, guards, SECRET, 30))
    app.include_router(admin.build_router(
        AdminService(repository, service, PASSWORD, store=_FakeStore()),
        guards, SECRET, 12,
    ))
    app.include_router(settings_router.build_router(
        _FakeStore(), None, guards, PASSWORD,
    ))

    @app.exception_handler(AppError)
    async def handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc)}
        )

    return TestClient(app), repository


def _operator(client):
    response = client.post("/api/admin/login", json={"password": PASSWORD})
    assert response.status_code == 200
    return response


def _open_team(client, name="משמרת א", password="sod-gadol"):
    response = client.post(
        "/api/admin/teams", json={"name": name, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- the door ----------------------------------------------------------------

def test_the_login_page_can_no_longer_open_a_team(world):
    client, repository = world
    response = client.post(
        "/api/workspace", json={"name": "צוות", "password": "sod-gadol"}
    )

    assert response.status_code == 403
    assert "צוות משמרות זהב" in response.json()["detail"]
    assert repository.teams == {}


def test_a_wrong_operator_password_is_refused_and_sets_no_cookie(world):
    client, _ = world
    response = client.post("/api/admin/login", json={"password": "nope"})

    assert response.status_code == 401
    assert ADMIN_COOKIE_NAME not in response.headers.get("set-cookie", "")


def test_the_operator_cookie_is_httponly_and_opens_the_console(world):
    client, _ = world
    cookie = _operator(client).headers["set-cookie"]

    assert ADMIN_COOKIE_NAME in cookie and "httponly" in cookie.lower()
    assert client.get("/api/admin/me").json()["role"] == ROLE_ADMIN


def test_an_unset_operator_password_keeps_the_console_locked():
    service = AdminService(_FakeAdminRepo(), None, "")
    with pytest.raises(AppError):
        service.login("")


def test_a_boss_cookie_does_not_open_the_console(world):
    client, _ = world
    client.cookies.set(COOKIE_NAME, issue(SECRET, "team-1", "boss", 1))

    assert client.get("/api/admin/teams").status_code == 401


def test_the_two_cookies_cannot_stand_in_for_each_other():
    admin_cookie = issue_admin(SECRET, 1)
    boss_cookie = issue(SECRET, "team-1", "boss", 1)

    assert read(SECRET, admin_cookie) is None
    assert read_admin(SECRET, boss_cookie) is None


# --- opening and controlling teams ------------------------------------------

def test_a_team_opened_by_the_operator_can_be_entered_by_its_manager(world):
    client, _ = world
    _operator(client)
    team = _open_team(client)

    assert team["name"] == "משמרת א" and team["active"] is True
    assert "password_hash" not in team
    login = client.post("/api/workspace/login", json={
        "team_id": team["id"], "password": "sod-gadol",
    })
    assert login.status_code == 200


def test_a_suspended_team_is_refused_at_the_door_and_under_open_sessions(world):
    client, _ = world
    _operator(client)
    team = _open_team(client)
    client.post("/api/workspace/login", json={
        "team_id": team["id"], "password": "sod-gadol",
    })
    assert client.get("/api/workspace/me").status_code == 200

    client.patch("/api/admin/teams/%s" % team["id"], json={"active": False})

    assert client.get("/api/workspace/me").status_code == 401
    login = client.post("/api/workspace/login", json={
        "team_id": team["id"], "password": "sod-gadol",
    })
    assert login.status_code == 403
    assert client.get("/api/workspace/teams").json() == []


def test_resuming_a_team_lets_it_back_in(world):
    client, _ = world
    _operator(client)
    team = _open_team(client)
    path = "/api/admin/teams/%s" % team["id"]
    client.patch(path, json={"active": False})
    client.patch(path, json={"active": True})

    login = client.post("/api/workspace/login", json={
        "team_id": team["id"], "password": "sod-gadol",
    })
    assert login.status_code == 200


def test_creating_takes_a_name_and_password_and_nothing_about_headcount(world):
    """How many employees a team has is its manager's call, made in their
    own roster -- the operator opens the door and sets the first password."""
    client, _ = world
    _operator(client)
    response = client.post("/api/admin/teams", json={
        "name": "צוות", "password": "sod-gadol", "max_employees": 3,
    })

    assert response.status_code == 200
    assert "max_employees" not in response.json()


def test_an_edit_applies_only_the_keys_it_sends(world):
    client, _ = world
    _operator(client)
    team = _open_team(client)
    path = "/api/admin/teams/%s" % team["id"]
    client.patch(path, json={"notes": "פלוגה ב"})

    updated = client.patch(path, json={"name": "משמרת ב"}).json()
    assert updated["name"] == "משמרת ב" and updated["notes"] == "פלוגה ב"


def test_the_operator_can_reset_a_forgotten_manager_password(world):
    client, _ = world
    _operator(client)
    team = _open_team(client)
    client.post(
        "/api/admin/teams/%s/password" % team["id"],
        json={"password": "hadash-123"},
    )

    login = client.post("/api/workspace/login", json={
        "team_id": team["id"], "password": "hadash-123",
    })
    assert login.status_code == 200


def test_deleting_needs_the_name_typed_back(world):
    client, repository = world
    _operator(client)
    team = _open_team(client, name="משמרת א")
    path = "/api/admin/teams/%s/delete" % team["id"]

    assert client.post(path, json={"confirm_name": "משמרת"}).status_code == 502
    assert team["id"] in repository.teams
    assert client.post(path, json={"confirm_name": "משמרת א"}).status_code == 200
    assert team["id"] not in repository.teams


def test_a_deleted_teams_open_session_stops_working(world):
    client, _ = world
    _operator(client)
    team = _open_team(client, name="משמרת א")
    client.post("/api/workspace/login", json={
        "team_id": team["id"], "password": "sod-gadol",
    })
    client.post(
        "/api/admin/teams/%s/delete" % team["id"],
        json={"confirm_name": "משמרת א"},
    )

    assert client.get("/api/workspace/me").status_code == 401


def test_the_operator_reaches_system_settings_without_the_password_header(world):
    client, _ = world
    _operator(client)

    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["openai_api_key"] == "********"
