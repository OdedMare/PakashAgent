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


def test_the_fair_fill_proposes_writes_nothing_and_approval_seats_it(repo):  # noqa: F811
    team = repo.create_team("משמרת א", "pw-team-1")
    repo.create_team_profile(team["id"], {"employees": [{"name": "דנה"}, {"name": "יוסי"},
                                                        {"name": "רון"}],
                                          "shifts": [{"name": "בוקר"}]})
    created = repo.create_complex("מכלול", "pw-commander")
    repo.set_complex_teams(created["id"], [team["id"]])
    # דנה cannot stand a duty on the 10th: a hard whole-day constraint.
    repo.set_availability(team["id"], "דנה", DAY, reason="קורס")
    client, _ = _app(repo)
    client.post("/api/complex/login", json={"complex_id": created["id"], "password": "pw-commander"})
    kitchen = client.post("/api/complex/duty-types", json={"name": "מטבח"}).json()
    # יוסי already stood one last week.
    assert client.post("/api/complex/duties", json={
        "duty_type_id": kitchen["id"], "team_id": team["id"], "employee": "יוסי",
        "duty_date": "2026-11-03", "blocks": False}).status_code == 200

    span = {"start": DAY, "end": "2026-11-11"}
    suggested = client.post("/api/complex/duties/suggest", params=span).json()
    picks = [(row["duty_date"], row["employee"]) for row in suggested["proposals"]]
    assert picks == [(DAY, "רון"), ("2026-11-11", "דנה")]
    assert suggested["unfilled"] == []
    assert client.get("/api/complex/duties", params=span).json()["duties"] == []

    approved = client.post("/api/complex/duties/approve", json={"rows": [
        {key: row[key] for key in ("duty_type_id", "team_id", "employee", "duty_date")}
        for row in suggested["proposals"]] + [
        {"duty_type_id": kitchen["id"], "team_id": team["id"], "employee": "יוסי", "duty_date": DAY}]})
    body = approved.json()
    assert len(body["saved"]) == 2
    assert [row["employee"] for row in body["failed"]] == ["יוסי"]  # the seat was taken
    assert "מאוישים" in body["failed"][0]["error"]

    result = client.get("/api/complex/duties/balance",
                        params={"start": "2026-11-01", "end": "2026-11-30"}).json()
    people = {row["employee"]: row["duty_load"] for row in result["people"]}
    assert people == {"דנה": 1, "יוסי": 1, "רון": 1}
    assert result["spread"]["gap"] == 0


def test_a_duty_on_a_draft_shift_vacates_it_and_queues_the_refill(repo):  # noqa: F811
    from app.bl.schedule_service import ScheduleService

    team = repo.create_team("משמרת א", "pw-team-1")
    shift = {"name": "בוקר", "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]}
    repo.create_team_profile(team["id"], {"workplace": {"name": "א"},
                                          "employees": [{"name": "דנה"}, {"name": "יוסי"}],
                                          "shifts": [shift]})
    created = repo.create_complex("מכלול", "pw-commander")
    repo.set_complex_teams(created["id"], [team["id"]])
    schedules = ScheduleService(repo, None)
    week = schedules.create_blank(team["id"], "2099-03-01", "2099-03-07")
    schedules.assign(team["id"], "בוקר", "2099-03-03", "דנה", schedule_id=week["id"])
    complexes = ComplexService(repo, WorkspaceService(repo))
    duties = ComplexDutyService(repo, complexes, notify=complexes.record, schedules=schedules)
    kitchen = duties.create_type(created["id"], {"name": "מטבח"})

    result = duties.assign(created["id"], kitchen["id"], team["id"], "דנה", "2099-03-03")

    assert [(c["shift_name"], c["outcome"]) for c in result["conflicts"]] == [("בוקר", "vacated")]
    stored = repo.get_schedule(week["id"], team["id"])
    assert [row["employee"] for row in stored["assignments"]] == []
    assert stored["generation"]["keep_existing"] is True
    removed = [row for row in repo.change_log(team["id"]) if row["action"] == "removed"]
    assert removed and removed[0]["reason"] == "תורנות מכלול: מטבח"
    assert removed[0]["actor"] == "commander:" + created["id"]
