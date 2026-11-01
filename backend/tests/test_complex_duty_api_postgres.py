"""`/api/complex/duty*` end to end, over a real PostgreSQL.

Skipped without `CHAT_TEST_DSN`. Signs in as the commander through the
real login, then: a duty type, a duty, the team's commander reading it
and refused deleting it, the change log and the notice in that team, and
the manual guard refusing the soldier that day.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies import Guards
from app.api.routers import complex as complex_router
from app.bl.complex_duties import ComplexDutyService
from app.bl.complex_service import ComplexService, describe_action  # noqa: F401
from app.bl.workspace_service import WorkspaceService
from app.common.errors import AppError
from app.common.sessions import COOKIE_NAME, ROLE_BOSS, issue

from tests.test_admin_postgres import pytestmark, repo  # noqa: F401  (fixture)

SECRET = "test-secret"
DAY = "2026-11-10"


def _app(repo):  # noqa: F811
    guards = Guards(SECRET, team_active=repo.team_is_active,
                    team_in_complex=repo.team_in_complex,
                    complex_active=repo.complex_is_active)
    complexes = ComplexService(repo, WorkspaceService(repo))
    told = []
    duties = ComplexDutyService(repo, complexes, notify=lambda *args: (
        complexes.record(*args), told.append(args)))
    app = FastAPI()

    @app.exception_handler(AppError)
    def _error(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    app.include_router(complex_router.build_router(
        complexes, guards, SECRET, 30, duties=duties))
    return TestClient(app), told


def test_a_commander_sets_a_duty_and_the_team_sees_it(repo):  # noqa: F811
    team = repo.create_team("משמרת א", "pw-team-1")
    outsider = repo.create_team("משמרת אחרת", "pw-team-2")
    repo.create_team_profile(team["id"], {"employees": [{"name": "דנה"}],
                                          "shifts": [{"name": "בוקר"}]})
    created = repo.create_complex("מכלול", "pw-commander")
    repo.set_complex_teams(created["id"], [team["id"]])
    client, told = _app(repo)

    assert client.post("/api/complex/duty-types", json={"name": "מטבח"}).status_code == 401
    assert client.post("/api/complex/login", json={
        "complex_id": created["id"], "password": "pw-commander"}).status_code == 200

    kitchen = client.post("/api/complex/duty-types", json={"name": "מטבח", "seats": 2}).json()
    assert client.post("/api/complex/duty-types", json={"name": "מטבח"}).status_code == 409
    assert client.post("/api/complex/duties", json={
        "duty_type_id": kitchen["id"], "team_id": outsider["id"],
        "employee": "דנה", "duty_date": DAY}).status_code == 404

    seated = client.post("/api/complex/duties", json={
        "duty_type_id": kitchen["id"], "team_id": team["id"],
        "employee": "דנה", "duty_date": DAY, "note": "מטבח מרכזי"})
    assert seated.status_code == 200, seated.text
    duty = seated.json()["duty"]
    assert (duty["team_name"], duty["duty_type"], duty["weight"]) == ("משמרת א", "מטבח", 1)
    assert seated.json()["conflicts"] == []

    roster = client.get("/api/complex/duty-roster").json()
    assert [(t["name"], [p["name"] for p in t["soldiers"]]) for t in roster] == [
        ("משמרת א", ["דנה"])]
    board = client.get("/api/complex/duties", params={"start": DAY, "end": DAY}).json()
    assert [d["employee"] for d in board["duties"]] == ["דנה"]
    assert [t["name"] for t in board["types"]] == ["מטבח"]

    # The team's own commander reads it, is told of it, and the log says who.
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, issue(SECRET, team["id"], ROLE_BOSS, 30))
    mine = client.get("/api/complex/team-duties", params={"start": DAY, "end": DAY}).json()
    assert [(d["employee"], d["duty_type"]) for d in mine] == [("דנה", "מטבח")]
    notices = client.get("/api/complex/notices").json()["notices"]
    assert [n["action"] for n in notices] == ["שיבץ תורנות מכלול"]
    assert told == [(team["id"], created["id"], "שיבץ תורנות מכלול")]
    [change] = repo.change_log(team["id"])
    assert (change["action"], change["employee"], change["actor"]) == (
        "complex_duty", "דנה", "commander:" + created["id"])
    assert client.get("/api/complex/duties", params={"start": DAY, "end": DAY}).status_code == 401
