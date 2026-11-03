"""A מכלול: several workplaces under one commander (D43).

What these pin down is the access story: the operator links existing teams
and issues the commander's password; the commander enters only linked
workplaces and holds a manager's powers there; unlinking ends that at once;
the workplace's own password stays the manager's; and the manager is told
what the commander changed.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies import Guards
from app.api.routers import admin, complex as complex_router, workspace
from app.bl.admin_service import AdminService
from app.bl.complex_service import ComplexService, describe_action
from app.bl.workspace_service import WorkspaceService
from app.common.actor import actor_of
from app.common.errors import AppError, AuthError, ConflictError, NotFoundError
from app.common.sessions import COMMANDER_COOKIE_NAME, COOKIE_NAME, read
from app.dal.repository.teams import hash_password, verify_password

from tests.test_admin_api import _FakeAdminRepo

SECRET = "test-secret"
PASSWORD = "010802"


class _FakeComplexRepo(_FakeAdminRepo):
    def __init__(self):
        super().__init__()
        self.complexes = {}
        self.notices = []

    def create_complex(self, name, password):
        complex_id = "c-%d" % (len(self.complexes) + 1)
        self.complexes[complex_id] = {
            "id": complex_id, "name": name, "notes": "", "active": True,
            "password_hash": hash_password(password),
        }
        return self.get_complex(complex_id)

    def get_complex(self, complex_id):
        if complex_id not in self.complexes:
            raise NotFoundError("המכלול לא נמצא")
        row = dict(self.complexes[complex_id])
        row.pop("password_hash")
        return row

    def admin_complexes(self):
        rows = []
        for complex_id in self.complexes:
            row = self.get_complex(complex_id)
            row["teams"] = [
                {"id": t["id"], "name": t["name"], "active": t["active"]}
                for t in self.teams.values() if t.get("complex_id") == complex_id
            ]
            rows.append(row)
        return rows

    def update_complex(self, complex_id, fields):
        self.get_complex(complex_id)
        self.complexes[complex_id].update(fields)

    def set_complex_password(self, complex_id, password):
        self.complexes[complex_id]["password_hash"] = hash_password(password)

    def set_complex_teams(self, complex_id, team_ids):
        for team_id in team_ids:
            if team_id not in self.teams:
                raise NotFoundError("אחד הצוותים לא נמצא")
            other = self.teams[team_id].get("complex_id")
            if other and other != complex_id:
                raise ConflictError("כבר משויך למכלול אחר")
        for team in self.teams.values():
            if team.get("complex_id") == complex_id and team["id"] not in team_ids:
                team["complex_id"] = None
        for team_id in team_ids:
            self.teams[team_id]["complex_id"] = complex_id

    def delete_complex(self, complex_id):
        self.complexes.pop(complex_id)
        for team in self.teams.values():
            if team.get("complex_id") == complex_id:
                team["complex_id"] = None

    def list_complexes(self):
        return [self.get_complex(c) for c in self.complexes
                if self.complexes[c]["active"]]

    def authenticate_commander(self, complex_id, password):
        row = self.complexes.get(complex_id)
        if row is None or not verify_password(password, row["password_hash"]):
            raise AuthError("שם המכלול או הסיסמה שגויים")
        return self.get_complex(complex_id)

    def complex_is_active(self, complex_id):
        row = self.complexes.get(complex_id)
        return bool(row and row["active"])

    def complex_teams(self, complex_id):
        return [
            {"id": t["id"], "name": t["name"], "active": t["active"],
             "has_profile": False, "shifts": [], "employees": 0}
            for t in self.teams.values() if t.get("complex_id") == complex_id
        ]

    def team_in_complex(self, team_id, complex_id):
        team = self.teams.get(team_id)
        return bool(
            team and team.get("complex_id") == complex_id and team["active"]
            and self.complex_is_active(complex_id)
        )

    def team_complex(self, team_id):
        complex_id = self.teams[team_id].get("complex_id")
        return {"id": complex_id, "name": self.complexes[complex_id]["name"]} \
            if complex_id else None

    def record_commander_notice(self, team_id, complex_name, action):
        self.notices.append({"team_id": team_id, "action": action, "seen": False})

    def commander_notices(self, team_id):
        return [n for n in self.notices if n["team_id"] == team_id and not n["seen"]]

    def mark_commander_notices_seen(self, team_id):
        for notice in self.notices:
            if notice["team_id"] == team_id:
                notice["seen"] = True


@pytest.fixture
def world():
    repository = _FakeComplexRepo()
    guards = Guards(
        SECRET, team_active=repository.team_is_active,
        team_in_complex=repository.team_in_complex,
        complex_active=repository.complex_is_active,
    )
    teams = WorkspaceService(repository)
    complexes = ComplexService(repository, teams)
    app = FastAPI()
    app.include_router(workspace.build_router(teams, guards, SECRET, 30))
    app.include_router(admin.build_router(
        AdminService(repository, teams, PASSWORD), guards, SECRET, 12,
        complexes=complexes,
    ))
    app.include_router(complex_router.build_router(complexes, guards, SECRET, 30))

    @app.get("/probe")
    def probe(session: dict = Depends(guards.manager())) -> dict:
        """A stand-in for every manager route."""
        return {"team_id": session["team_id"], "manager_id": session["manager_id"],
                "actor": actor_of(session)}

    @app.exception_handler(AppError)
    async def handler(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    client = TestClient(app)
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    ids = [
        client.post("/api/admin/teams", json={"name": name, "password": "sod-gadol"}).json()["id"]
        for name in ("משמרת א", "משמרת ב", "משמרת ג")
    ]
    return client, repository, complexes, ids


def _open_complex(client, team_ids, password="mefaked1"):
    response = client.post("/api/admin/complexes", json={
        "name": "מכלול צפון", "password": password, "team_ids": team_ids,
    })
    assert response.status_code == 200, response.text
    return response.json()


def _as_commander(client, complex_id, password="mefaked1"):
    client.cookies.clear()
    response = client.post("/api/complex/login", json={
        "complex_id": complex_id, "password": password,
    })
    assert response.status_code == 200, response.text


def test_the_operator_links_existing_teams_into_a_complex(world):
    client, repository, _, ids = world
    created = _open_complex(client, ids[:2])

    assert {t["id"] for t in created["teams"]} == set(ids[:2])
    assert "password_hash" not in created
    assert repository.teams[ids[2]].get("complex_id") is None


def test_a_team_cannot_sit_in_two_complexes(world):
    client, _, _, ids = world
    _open_complex(client, ids[:1])
    response = client.post("/api/admin/complexes", json={
        "name": "מכלול דרום", "password": "mefaked2", "team_ids": ids[:1],
    })
    assert response.status_code == 409


def test_the_commander_enters_only_linked_workplaces(world):
    client, _, _, ids = world
    created = _open_complex(client, ids[:2])
    _as_commander(client, created["id"])

    me = client.get("/api/complex/me").json()
    assert {t["id"] for t in me["teams"]} == set(ids[:2])
    assert client.post("/api/complex/teams/%s/enter" % ids[2]).status_code == 404

    assert client.post("/api/complex/teams/%s/enter" % ids[0]).status_code == 200
    probe = client.get("/probe").json()
    assert probe["team_id"] == ids[0]
    assert probe["actor"] == "commander:" + created["id"]
    assert probe["manager_id"] == "commander-" + created["id"]
    session = read(SECRET, client.cookies.get(COOKIE_NAME))
    assert session["role"] == "boss" and session["commander"] == created["id"]


def test_a_wrong_commander_password_is_refused(world):
    client, _, _, ids = world
    created = _open_complex(client, ids[:1])
    client.cookies.clear()
    response = client.post("/api/complex/login", json={
        "complex_id": created["id"], "password": "nope-nope",
    })
    assert response.status_code == 401
    assert COMMANDER_COOKIE_NAME not in response.cookies


def test_unlinking_a_workplace_ends_the_commanders_access_at_once(world):
    client, _, _, ids = world
    created = _open_complex(client, ids[:2])
    _as_commander(client, created["id"])
    client.post("/api/complex/teams/%s/enter" % ids[0])
    team_cookie = client.cookies.get(COOKIE_NAME)
    assert client.get("/probe").status_code == 200

    client.post("/api/admin/login", json={"password": PASSWORD})
    client.patch("/api/admin/complexes/%s" % created["id"], json={"team_ids": [ids[1]]})

    client.cookies.set(COOKIE_NAME, team_cookie)
    assert client.get("/probe").status_code == 401


def test_the_manager_password_stays_the_managers(world):
    client, _, _, ids = world
    created = _open_complex(client, ids[:1])
    _as_commander(client, created["id"])
    client.post("/api/complex/teams/%s/enter" % ids[0])

    response = client.post("/api/workspace/password", json={
        "current": "sod-gadol", "replacement": "hadash-123",
    })
    assert response.status_code == 403


def test_the_manager_still_signs_in_with_the_team_password(world):
    client, _, _, ids = world
    _open_complex(client, ids[:1])
    client.cookies.clear()
    response = client.post("/api/workspace/login", json={
        "team_id": ids[0], "password": "sod-gadol",
    })
    assert response.status_code == 200
    me = client.get("/api/workspace/me").json()
    assert me["commander"] is False and me["complex"]["name"] == "מכלול צפון"
    assert client.get("/probe").json()["actor"].startswith("boss")


def test_the_manager_reads_and_clears_what_the_commander_changed(world):
    client, _, complexes, ids = world
    created = _open_complex(client, ids[:1])
    complexes.record(ids[0], created["id"], "פרסם סידור")

    client.cookies.clear()
    client.post("/api/workspace/login", json={"team_id": ids[0], "password": "sod-gadol"})
    assert [n["action"] for n in client.get("/api/complex/notices").json()["notices"]] \
        == ["פרסם סידור"]
    client.post("/api/complex/notices/seen")
    assert client.get("/api/complex/notices").json()["notices"] == []


def test_a_suspended_complex_signs_its_commander_out(world):
    client, _, _, ids = world
    created = _open_complex(client, ids[:1])
    _as_commander(client, created["id"])
    commander_cookie = client.cookies.get(COMMANDER_COOKIE_NAME)

    client.post("/api/admin/login", json={"password": PASSWORD})
    client.patch("/api/admin/complexes/%s" % created["id"], json={"active": False})

    client.cookies.set(COMMANDER_COOKIE_NAME, commander_cookie)
    assert client.get("/api/complex/me").status_code == 401


def test_deleting_a_complex_leaves_its_teams_standing(world):
    client, repository, _, ids = world
    created = _open_complex(client, ids[:2])
    bad = client.post("/api/admin/complexes/%s/delete" % created["id"],
                      json={"confirm_name": "לא זה"})
    assert bad.status_code == 502  # AgentError, as for deleting a team
    response = client.post("/api/admin/complexes/%s/delete" % created["id"],
                           json={"confirm_name": "מכלול צפון"})
    assert response.status_code == 200
    assert set(repository.teams) == set(ids)
    assert all(not t.get("complex_id") for t in repository.teams.values())


def test_what_the_manager_is_told_reads_in_their_words():
    assert describe_action("GET", "/api/schedule/current") is None
    assert describe_action("POST", "/api/schedule/check") is None
    assert describe_action("POST", "/api/schedule/assign") == "שינה שיבוץ בלוח"
    assert describe_action("POST", "/api/schedule/abc/publish") == "פרסם סידור"
    assert describe_action("PUT", "/api/profile") == "שינה את הגדרות המשמרת"
    assert describe_action("POST", "/api/agent/chats/x/messages/y/apply") \
        == "אישר שינוי מהשיחה עם הסוכן"
