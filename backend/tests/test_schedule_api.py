"""The management area's HTTP contract, over a fake repository and model.

Three things here are the point of the feature and are asserted directly:

- **A member cannot write.** Every mutating route depends on `guards.boss()`,
  so a member's cookie is refused whichever URL it is aimed at (D5).
- **One workspace cannot reach another's schedule**, even holding its id
  (D10). A cross-team miss reads as "not found", never as "not yours".
- **Warnings never block.** A schedule that breaks every rule still returns
  200 and still renders (D3).
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies import Guards
from app.api.routers import schedules
from app.bl.schedule_service import ScheduleService
from app.common.errors import AppError, NotFoundError
from app.common.sessions import COOKIE_NAME, ROLE_BOSS, ROLE_MEMBER, issue

TEAM = "team-a"
OTHER_TEAM = "team-b"
SECRET = "test-secret"

MORNING = "בוקר"
EVENING = "צהריים"

PROFILE = {
    "workplace": {"name": "מוקד", "mission": "מענה", "planning_horizon": "שבוע"},
    "employees": [
        {"name": "דנה", "eligible_shifts": [MORNING]},
        {"name": "יוסי", "eligible_shifts": [MORNING, EVENING]},
    ],
    "shifts": [{
        "name": MORNING, "start_time": "07:00", "end_time": "15:00",
        "days": [], "is_on_call": False, "hour_weight": 1.0,
        "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
    }],
    "rules": [],
}


class _FakeScheduleRepo:
    """In-memory stand-in that filters by team exactly as the SQL does."""

    def __init__(self):
        self.schedules = {}
        self.slots = {}
        self.assignment_rows = {}
        self.availability_rows = []
        self.changes = []
        self.requests = []
        self.profiles = {TEAM: PROFILE, OTHER_TEAM: PROFILE}
        self._n = 0

    def _id(self, prefix):
        self._n += 1
        return "%s-%d" % (prefix, self._n)

    def team_profile(self, team_id):
        return self.profiles.get(team_id)

    def create_schedule(self, team_id, starts_on, ends_on):
        schedule_id = self._id("sched")
        self.schedules[schedule_id] = {
            "id": schedule_id, "team_id": team_id, "starts_on": starts_on,
            "ends_on": ends_on, "status": "draft",
        }
        self.slots[schedule_id] = []
        self.assignment_rows[schedule_id] = []
        return self.get_schedule(schedule_id, team_id)

    def get_schedule(self, schedule_id, team_id):
        row = self.schedules.get(schedule_id)
        # A schedule in another workspace is indistinguishable from one that
        # does not exist -- distinguishing them would turn this into an
        # oracle for which rows live in workspaces the caller cannot see.
        if row is None or row["team_id"] != team_id:
            raise NotFoundError("הפריט לא נמצא")
        view = dict(row)
        view["slots"] = self.slots.get(schedule_id, [])
        view["assignments"] = self.assignments(schedule_id, team_id)
        return view

    def list_schedules(self, team_id):
        return [
            {k: row[k] for k in ("id", "starts_on", "ends_on", "status")}
            for row in self.schedules.values() if row["team_id"] == team_id
        ]

    def current_schedule(self, team_id, published_only=False):
        for row in reversed(list(self.schedules.values())):
            if row["team_id"] != team_id:
                continue
            if published_only and row["status"] != "published":
                continue
            return self.get_schedule(row["id"], team_id)
        return None

    def set_schedule_status(self, schedule_id, team_id, status):
        self.get_schedule(schedule_id, team_id)
        self.schedules[schedule_id]["status"] = status
        return self.get_schedule(schedule_id, team_id)

    def delete_schedule(self, schedule_id, team_id):
        self.get_schedule(schedule_id, team_id)
        del self.schedules[schedule_id]

    def replace_slots(self, schedule_id, team_id, slots):
        self.get_schedule(schedule_id, team_id)
        self.slots[schedule_id] = [
            dict(slot, id=self._id("slot"), team_id=team_id) for slot in slots
        ]
        return self.slots[schedule_id]

    def find_slot(self, schedule_id, team_id, shift_name, slot_date):
        self.get_schedule(schedule_id, team_id)
        for slot in self.slots.get(schedule_id, []):
            if (slot["shift_name"] == shift_name
                    and slot["slot_date"] == slot_date):
                return slot
        return None

    def assignments(self, schedule_id, team_id):
        rows = []
        for row in self.assignment_rows.get(schedule_id, []):
            slot = next(
                s for s in self.slots[schedule_id] if s["id"] == row["slot_id"]
            )
            rows.append(dict(
                row, shift=slot["shift_name"], date=slot["slot_date"],
                start_time=slot.get("start_time", ""),
                end_time=slot.get("end_time", ""),
                is_on_call=slot.get("is_on_call", False),
                source=row.get("source", "agent"),
            ))
        return rows

    def replace_assignments(self, schedule_id, team_id, assignments):
        self.get_schedule(schedule_id, team_id)
        for item in assignments:
            assert item["reason"].strip(), "reason is required (D8)"
        self.assignment_rows[schedule_id] = [
            {"id": self._id("asg"), "slot_id": item["slot_id"],
             "employee": item["employee"], "reason": item["reason"],
             "schedule_id": schedule_id,
             "source": item.get("source") or "agent"}
            for item in assignments
        ]
        return self.assignments(schedule_id, team_id)

    def add_assignment(self, schedule_id, team_id, slot_id, employee, reason,
                       source="agent"):
        assert reason.strip(), "reason is required (D8)"
        assert source in ("agent", "manager", "imported"), source
        self.get_schedule(schedule_id, team_id)
        # The real table is UNIQUE (slot_id, employee) and the insert says
        # DO NOTHING, so placing the same person on the same slot twice is a
        # success that changes nothing. Mirrored here because the manual path
        # depends on that being the behaviour rather than a duplicate row.
        for existing in self.assignment_rows[schedule_id]:
            if (existing["slot_id"] == slot_id
                    and existing["employee"] == employee):
                return dict(existing)
        row = {"id": self._id("asg"), "slot_id": slot_id,
               "employee": employee, "reason": reason,
               "schedule_id": schedule_id, "source": source}
        self.assignment_rows[schedule_id].append(row)
        return row

    def remove_assignment(self, assignment_id, team_id):
        for schedule_id, rows in self.assignment_rows.items():
            if self.schedules[schedule_id]["team_id"] != team_id:
                continue
            self.assignment_rows[schedule_id] = [
                row for row in rows if row["id"] != assignment_id
            ]

    def move_assignment(self, assignment_id, team_id, slot_id, reason,
                        employee=None):
        assert reason.strip(), "reason is required (D8)"
        for schedule_id, rows in self.assignment_rows.items():
            if self.schedules[schedule_id]["team_id"] != team_id:
                continue
            for row in rows:
                if row["id"] == assignment_id:
                    row["slot_id"] = slot_id
                    row["reason"] = reason
                    if employee:
                        row["employee"] = employee
                    return dict(row)
        raise NotFoundError("השיבוץ לא נמצא")

    def set_availability(self, team_id, employee, constraint_date,
                         shift_name="", available=False, reason="",
                         source="manager"):
        row = {
            "id": self._id("av"), "team_id": team_id, "employee": employee,
            "constraint_date": constraint_date, "shift_name": shift_name,
            "available": available, "reason": reason, "source": source,
        }
        self.availability_rows = [
            existing for existing in self.availability_rows
            if not (existing["team_id"] == team_id
                    and existing["employee"] == employee
                    and existing["constraint_date"] == constraint_date
                    and existing["shift_name"] == shift_name)
        ]
        self.availability_rows.append(row)
        return row

    def availability(self, team_id, starts_on=None, ends_on=None,
                     employee=None):
        rows = [
            row for row in self.availability_rows
            if row["team_id"] == team_id
        ]
        if starts_on:
            rows = [r for r in rows if r["constraint_date"] >= starts_on]
        if ends_on:
            rows = [r for r in rows if r["constraint_date"] <= ends_on]
        if employee:
            rows = [r for r in rows if r["employee"] == employee]
        return rows

    def delete_availability(self, row_id, team_id):
        self.availability_rows = [
            row for row in self.availability_rows
            if not (row["id"] == row_id and row["team_id"] == team_id)
        ]

    def append_change(self, team_id, action, schedule_id=None, employee="",
                      replaced_employee="", slot_date=None, shift_name="",
                      reason="", agent_reason=""):
        row = {
            "id": self._id("chg"), "team_id": team_id, "action": action,
            "schedule_id": schedule_id, "employee": employee,
            "replaced_employee": replaced_employee, "slot_date": slot_date,
            "shift_name": shift_name, "reason": reason,
            "agent_reason": agent_reason,
        }
        self.changes.append(row)
        return row

    def change_log(self, team_id, schedule_id=None, limit=100):
        rows = [r for r in self.changes if r["team_id"] == team_id]
        if schedule_id:
            rows = [r for r in rows if r["schedule_id"] == schedule_id]
        return list(reversed(rows))[:limit]

    def list_requests(self, team_id, employee=None, status=None):
        rows = [r for r in self.requests if r["team_id"] == team_id]
        if status:
            rows = [r for r in rows if r["status"] == status]
        return rows


class _ScriptedLlm:
    def __init__(self, answers=None):
        self._answers = list(answers or [])

    def complete_json(self, system, user, schema=None):
        if not self._answers:
            raise AssertionError("model called more times than scripted")
        return self._answers.pop(0)


def _generation(assignments, notes=None):
    return {"assignments": assignments, "notes": notes or [],
            "summary": "סידור השבוע"}


def _build_app(answers=None):
    repository = _FakeScheduleRepo()
    llm = _ScriptedLlm(answers)
    guards = Guards(SECRET)
    app = FastAPI()
    app.include_router(
        schedules.build_router(ScheduleService(repository, llm), guards)
    )

    @app.exception_handler(AppError)
    async def handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc)}
        )

    return app, repository


def _client(app, role=ROLE_BOSS, team=TEAM):
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, issue(SECRET, team, role, 30))
    return client


# -- generating ------------------------------------------------------------

def test_generating_stores_a_draft_with_reasons():
    app, repo = _build_app([_generation([
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-17",
         "reason": "דנה מוסמכת לבוקר"},
    ])])
    response = _client(app).post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["assignments"][0]["reason"] == "דנה מוסמכת לבוקר"


def test_generating_without_a_finished_interview_is_refused():
    """No profile means no shift vocabulary, and guessing one is exactly
    the hardcoding D9 forbids."""
    app, repo = _build_app([])
    repo.profiles[TEAM] = None
    response = _client(app).post("/api/schedule/generate", json={})
    assert response.status_code == 502
    assert "ראיון" in response.json()["detail"]


def test_a_generated_schedule_carries_its_warnings_and_still_returns_200():
    """D3: warnings are advisory. A schedule that breaks a rule still renders."""
    app, _ = _build_app([_generation([
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-%02d" % day,
         "reason": "כיסוי"}
        for day in range(17, 25)
    ])])
    response = _client(app).post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-24",
    })
    assert response.status_code == 200
    codes = {warning["code"] for warning in response.json()["warnings"]}
    assert "consecutive" in codes
    # The schedule is still there in full, not withheld.
    assert len(response.json()["assignments"]) == 8


# -- the management overview ----------------------------------------------

def test_the_overview_returns_roster_vocabulary_and_period():
    app, _ = _build_app([_generation([
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-17",
         "reason": "מוסמכת"},
    ])])
    client = _client(app)
    client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    body = client.get("/api/schedule/overview").json()
    assert [row["name"] for row in body["employees"]] == ["דנה", "יוסי"]
    assert [row["name"] for row in body["shifts"]] == [MORNING]
    assert body["schedule"]["assignments"]


def test_the_overview_carries_the_periods_numbers():
    """The charts' figures ride along on the overview the screen already
    fetches, so the panel and the calendar beside it can never be a refresh
    apart. Pinned through the HTTP contract because the Pydantic models are
    what the browser actually receives -- a field added to `shift_stats` but
    missing from `ShiftStats` would be silently dropped here.
    """
    app, _ = _build_app([_generation([
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-17",
         "reason": "מוסמכת"},
    ])])
    client = _client(app)
    client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })

    stats = client.get("/api/schedule/overview").json()["stats"]

    assert stats["total_shifts"] == 1
    assert stats["people_working"] == 1
    # Everyone on the roster is present, including the person with no
    # shifts -- that zero is the whole point of the per-person chart.
    assert {row["employee"] for row in stats["by_employee"]} == {"דנה", "יוסי"}
    assert stats["coverage"]["assigned"] == 1


def test_the_overview_carries_zeroed_stats_before_anything_is_built():
    """The state the management screen opens in.

    The panel renders whatever arrives, so "no schedule yet" has to be a
    well-formed shape rather than a null the client special-cases.
    """
    app, _ = _build_app([])

    stats = _client(app).get("/api/schedule/overview").json()["stats"]

    assert stats["total_shifts"] == 0
    assert stats["coverage"]["required"] == 0


def test_a_member_sees_only_published_periods():
    """A draft is the manager's working state; publishing makes it the team's."""
    app, _ = _build_app([_generation([])])
    boss = _client(app)
    created = boss.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()

    member = _client(app, role=ROLE_MEMBER)
    assert member.get("/api/schedule/overview").json()["schedule"] is None

    boss.post("/api/schedule/%s/publish" % created["id"])
    assert member.get("/api/schedule/overview").json()["schedule"] is not None


# -- D18: the manual path -------------------------------------------------

def test_opening_a_blank_period_calls_no_model():
    """The authoring half of D6. `_ScriptedLlm` raises if it is called at
    all, so an empty answer list is the assertion: building a grid is
    arithmetic over the declared vocabulary, not a generation."""
    app, _ = _build_app([])
    response = _client(app).post("/api/schedule/blank", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    # The grid exists; nobody is on it yet.
    assert body["slots"], "a blank period still has its slots"
    assert body["assignments"] == []


def test_a_blank_period_without_a_finished_interview_is_refused():
    """Skipping the agent does not mean skipping the interview: without the
    shift vocabulary there is no grid to build (D9)."""
    app, repo = _build_app([])
    repo.profiles[TEAM] = None
    response = _client(app).post("/api/schedule/blank", json={})
    assert response.status_code == 502
    assert "ראיון" in response.json()["detail"]


def test_a_manual_assignment_is_marked_as_the_managers_and_calls_no_model():
    app, repo = _build_app([])
    client = _client(app)
    client.post("/api/schedule/blank", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    response = client.post("/api/schedule/assign", json={
        "shift_name": MORNING, "slot_date": "2026-08-17",
        "employee": "דנה", "reason": "דנה ביקשה את הבוקר הזה",
    })
    assert response.status_code == 200
    rows = response.json()["assignments"]
    assert len(rows) == 1
    assert rows[0]["employee"] == "דנה"
    # D18: provenance is recorded, so the agent and the manager are
    # distinguishable later rather than only by how their prose reads.
    assert rows[0]["source"] == "manager"
    assert rows[0]["reason"] == "דנה ביקשה את הבוקר הזה"


def test_a_manual_assignment_without_a_reason_still_carries_one():
    """D8 is answered by a different voice, not relaxed. The row says a
    person placed it rather than inventing a judgment the agent never made."""
    app, _ = _build_app([])
    client = _client(app)
    client.post("/api/schedule/blank", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    response = client.post("/api/schedule/assign", json={
        "shift_name": MORNING, "slot_date": "2026-08-17", "employee": "דנה",
    })
    assert response.status_code == 200
    assert response.json()["assignments"][0]["reason"].strip()


def test_a_manual_assignment_is_recorded_in_the_change_log():
    app, repo = _build_app([])
    client = _client(app)
    client.post("/api/schedule/blank", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    client.post("/api/schedule/assign", json={
        "shift_name": MORNING, "slot_date": "2026-08-17",
        "employee": "דנה", "reason": "כיסוי בוקר",
    })
    actions = [row["action"] for row in repo.changes]
    assert "opened" in actions
    assert "assigned" in actions
    placed = [row for row in repo.changes if row["action"] == "assigned"][0]
    assert placed["employee"] == "דנה"
    assert placed["reason"] == "כיסוי בוקר"


def test_assigning_the_same_person_twice_changes_nothing():
    """The table is UNIQUE (slot_id, employee) and the insert does nothing on
    conflict, so a double click is a success that added no duplicate."""
    app, _ = _build_app([])
    client = _client(app)
    client.post("/api/schedule/blank", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    body = {"shift_name": MORNING, "slot_date": "2026-08-17",
            "employee": "דנה"}
    first = client.post("/api/schedule/assign", json=body).json()
    second = client.post("/api/schedule/assign", json=body).json()
    assert len(second["assignments"]) == 1
    assert first["assigned"] == second["assigned"]


def test_assigning_onto_a_shift_that_does_not_run_is_a_404():
    app, _ = _build_app([])
    client = _client(app)
    client.post("/api/schedule/blank", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    response = client.post("/api/schedule/assign", json={
        "shift_name": EVENING, "slot_date": "2026-08-17", "employee": "דנה",
    })
    assert response.status_code == 404


def test_a_manual_schedule_still_carries_its_warnings():
    """D3 holds on the manual path too: the audit reports, and a hand-built
    week that breaks a rule still returns 200 and still renders."""
    app, _ = _build_app([])
    client = _client(app)
    client.post("/api/schedule/blank", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-24",
    })
    for day in range(17, 25):
        client.post("/api/schedule/assign", json={
            "shift_name": MORNING, "slot_date": "2026-08-%02d" % day,
            "employee": "דנה",
        })
    response = client.get("/api/schedule/overview")
    assert response.status_code == 200
    schedule = response.json()["schedule"]
    codes = {warning["code"] for warning in schedule["warnings"]}
    assert "consecutive" in codes
    # Reported, never withheld.
    assert len(schedule["assignments"]) == 8


def test_unassigning_removes_the_row_and_logs_it():
    app, repo = _build_app([])
    client = _client(app)
    client.post("/api/schedule/blank", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    placed = client.post("/api/schedule/assign", json={
        "shift_name": MORNING, "slot_date": "2026-08-17", "employee": "דנה",
    }).json()
    assignment_id = placed["assignments"][0]["id"]

    response = client.post("/api/schedule/unassign", json={
        "assignment_id": assignment_id, "reason": "דנה התחלפה",
    })
    assert response.status_code == 200
    assert response.json()["assignments"] == []
    removed = [row for row in repo.changes if row["action"] == "removed"][0]
    assert removed["employee"] == "דנה"
    assert removed["reason"] == "דנה התחלפה"


def test_unassigning_something_that_is_not_there_is_a_404():
    app, _ = _build_app([])
    client = _client(app)
    client.post("/api/schedule/blank", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    response = client.post("/api/schedule/unassign", json={
        "assignment_id": "nope",
    })
    assert response.status_code == 404


def test_a_generated_assignment_is_marked_as_the_agents():
    """The other side of D18: nothing about the manual path changes what a
    generated row says about itself."""
    app, _ = _build_app([_generation([
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-17",
         "reason": "דנה מוסמכת לבוקר"},
    ])])
    response = _client(app).post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    assert response.json()["assignments"][0]["source"] == "agent"


def test_one_workspace_cannot_assign_into_anothers_schedule():
    app, _ = _build_app([])
    created = _client(app).post("/api/schedule/blank", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()
    intruder = _client(app, team=OTHER_TEAM)
    response = intruder.post("/api/schedule/assign", json={
        "shift_name": MORNING, "slot_date": "2026-08-17",
        "employee": "דנה", "schedule_id": created["id"],
    })
    assert response.status_code == 404


# -- D5: employees are read-only ------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/schedule/generate", {}),
    ("post", "/api/schedule/blank", {}),
    ("post", "/api/schedule/assign",
     {"shift_name": MORNING, "slot_date": "2026-08-17", "employee": "דנה"}),
    ("post", "/api/schedule/unassign", {"assignment_id": "a"}),
    ("post", "/api/schedule/propose", {"request": "דנה חולה"}),
    ("post", "/api/schedule/apply",
     {"schedule_id": "s", "operations": [], "reason": "מחלה"}),
    ("post", "/api/schedule/move",
     {"assignment_id": "a", "shift_name": MORNING,
      "slot_date": "2026-08-17", "reason": "מחלה"}),
    ("post", "/api/schedule/constraints",
     {"employee": "דנה", "constraint_date": "2026-08-17"}),
    ("delete", "/api/schedule/constraints/x", None),
    ("delete", "/api/schedule/some-id", None),
])
def test_a_member_cannot_reach_any_mutation(method, path, body):
    """D5, enforced by `guards.boss()` rather than by convention.

    Parameterised over every mutating route so a route added later without a
    boss guard fails here rather than shipping.
    """
    app, _ = _build_app([])
    member = _client(app, role=ROLE_MEMBER)
    response = getattr(member, method)(
        path, **({"json": body} if body is not None else {})
    )
    assert response.status_code == 401


# -- D10: tenant isolation -------------------------------------------------

def test_another_workspace_cannot_read_a_schedule_by_id():
    app, _ = _build_app([_generation([])])
    created = _client(app).post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()

    intruder = _client(app, team=OTHER_TEAM)
    response = intruder.get("/api/schedule/%s" % created["id"])
    # 404, not 403: a distinct "wrong team" would confirm the id is real.
    assert response.status_code == 404


def test_another_workspace_cannot_publish_a_schedule_by_id():
    app, _ = _build_app([_generation([])])
    created = _client(app).post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()
    intruder = _client(app, team=OTHER_TEAM)
    assert intruder.post(
        "/api/schedule/%s/publish" % created["id"]
    ).status_code == 404


def test_constraints_are_scoped_to_the_workspace():
    app, _ = _build_app([])
    _client(app).post("/api/schedule/constraints", json={
        "employee": "דנה", "constraint_date": "2026-08-20",
        "reason": "מחלה",
    })
    intruder = _client(app, team=OTHER_TEAM)
    assert intruder.get("/api/schedule/constraints/list").json() == []


# -- the change loop -------------------------------------------------------

def test_a_change_without_a_reason_is_answered_by_asking():
    app, _ = _build_app([
        _generation([{"employee": "דנה", "shift": MORNING,
                      "date": "2026-08-17", "reason": "מוסמכת"}]),
        {"reply": "למה דנה לא מגיעה?", "needs_reason": True,
         "agent_reason": "", "operations": [], "constraints": []},
    ])
    client = _client(app)
    client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    proposal = client.post("/api/schedule/propose", json={
        "request": "תוריד את דנה",
    }).json()
    assert proposal["needs_reason"] is True
    assert proposal["operations"] == []


def test_proposing_persists_nothing():
    """The two-step contract: a proposal is a proposal until confirmed."""
    app, repo = _build_app([
        _generation([{"employee": "דנה", "shift": MORNING,
                      "date": "2026-08-17", "reason": "מוסמכת"}]),
        {"reply": "אציע להוריד את דנה", "needs_reason": False,
         "agent_reason": "דנה חולה, יוסי פנוי",
         "operations": [{"action": "remove", "employee": "דנה",
                         "shift": MORNING, "date": "2026-08-17",
                         "reason": "חולה"}],
         "constraints": []},
    ])
    client = _client(app)
    created = client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()
    before = len(repo.assignment_rows[created["id"]])

    client.post("/api/schedule/propose", json={
        "request": "דנה חולה", "reason": "מחלה",
    })
    assert len(repo.assignment_rows[created["id"]]) == before


def test_applying_a_confirmed_change_records_both_reasons():
    """D8: the manager's reason and the agent's both land in the log."""
    app, repo = _build_app([
        _generation([{"employee": "דנה", "shift": MORNING,
                      "date": "2026-08-17", "reason": "מוסמכת"}]),
    ])
    client = _client(app)
    created = client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()

    response = client.post("/api/schedule/apply", json={
        "schedule_id": created["id"],
        "operations": [{"action": "remove", "employee": "דנה",
                        "shift": MORNING, "date": "2026-08-17",
                        "reason": "דנה חולה"}],
        "reason": "מחלה",
        "agent_reason": "אין תחליף זמין",
    })
    assert response.status_code == 200
    entry = next(
        row for row in repo.changes if row["action"] == "removed"
    )
    assert entry["reason"] == "מחלה"
    assert entry["agent_reason"] == "דנה חולה"


def test_applying_without_a_reason_is_rejected_by_validation():
    """By apply time the manager has been asked; a blank reason now would be
    a hole in the only history the system keeps."""
    app, _ = _build_app([])
    response = _client(app).post("/api/schedule/apply", json={
        "schedule_id": "s", "operations": [], "reason": "",
    })
    assert response.status_code == 422


# -- the drag, which is a proposal ----------------------------------------

def test_a_confirmed_drag_moves_the_assignment_and_logs_the_reason():
    """Dragging is a way of proposing a change, not a way around D8.

    The gesture opens a confirmation; this is what that dialog sends, and it
    carries the manager's reason exactly as a spoken change does.
    """
    app, repo = _build_app([
        _generation([{"employee": "דנה", "shift": MORNING,
                      "date": "2026-08-17", "reason": "מוסמכת"}]),
    ])
    client = _client(app)
    created = client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()
    assignment = created["assignments"][0]

    response = client.post("/api/schedule/move", json={
        "assignment_id": assignment["id"],
        "shift_name": MORNING,
        "slot_date": "2026-08-18",
        "reason": "דנה ביקשה להחליף יום",
    })
    assert response.status_code == 200
    moved = response.json()["assignments"][0]
    assert moved["date"] == "2026-08-18"
    entry = next(row for row in repo.changes if row["action"] == "moved")
    assert entry["reason"] == "דנה ביקשה להחליף יום"


def test_a_drag_without_a_reason_is_rejected():
    """The confirmation dialog is what collects it; an empty one never
    reaches the server."""
    app, _ = _build_app([])
    response = _client(app).post("/api/schedule/move", json={
        "assignment_id": "a", "shift_name": MORNING,
        "slot_date": "2026-08-18", "reason": "",
    })
    assert response.status_code == 422


# -- constraints -----------------------------------------------------------

def test_a_constraint_is_recorded_with_its_source():
    """`source` records where the information came from, not who typed it:
    employees have no account and never write here (D5/D10)."""
    app, _ = _build_app([])
    client = _client(app)
    response = client.post("/api/schedule/constraints", json={
        "employee": "דנה", "constraint_date": "2026-08-20",
        "reason": "תואר", "source": "employee_reported",
    })
    assert response.status_code == 200
    assert response.json()["source"] == "employee_reported"


def test_a_recorded_constraint_shows_up_as_a_warning_when_contradicted():
    """The audit reads a constraint with no shift as covering the whole day."""
    app, _ = _build_app([_generation([
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-17",
         "reason": "כיסוי"},
    ])])
    client = _client(app)
    client.post("/api/schedule/constraints", json={
        "employee": "דנה", "constraint_date": "2026-08-17",
        "reason": "מילואים",
    })
    body = client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()
    codes = {warning["code"] for warning in body["warnings"]}
    assert "unavailable" in codes


def test_restating_a_constraint_replaces_rather_than_duplicates():
    """Two rows saying the same thing would double every warning it causes."""
    app, repo = _build_app([])
    client = _client(app)
    for reason in ("מחלה", "מילואים"):
        client.post("/api/schedule/constraints", json={
            "employee": "דנה", "constraint_date": "2026-08-20",
            "reason": reason,
        })
    rows = client.get("/api/schedule/constraints/list").json()
    assert len(rows) == 1
    assert rows[0]["reason"] == "מילואים"


def test_the_team_can_read_constraints_but_not_write_them():
    app, _ = _build_app([])
    _client(app).post("/api/schedule/constraints", json={
        "employee": "דנה", "constraint_date": "2026-08-20", "reason": "תואר",
    })
    member = _client(app, role=ROLE_MEMBER)
    assert len(member.get("/api/schedule/constraints/list").json()) == 1
    assert member.post("/api/schedule/constraints", json={
        "employee": "יוסי", "constraint_date": "2026-08-21",
    }).status_code == 401


def test_the_change_log_is_readable_as_history():
    app, _ = _build_app([_generation([])])
    client = _client(app)
    client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })
    history = client.get("/api/schedule/history/list").json()
    assert any(row["action"] == "generated" for row in history)


# -- the agent speaking first ----------------------------------------------

def test_the_agent_briefs_the_manager_unprompted():
    """The one route the manager did not initiate (D15)."""
    app, _ = _build_app([
        _generation([]),
        {"headline": "יש חור בשלישי", "quiet": False, "items": [
            {"text": "משמרת בוקר של שלישי ריקה", "kind": "gap",
             "suggestion": "מי יכול לכסות את בוקר שלישי?"},
        ]},
    ])
    client = _client(app)
    client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    })

    body = client.post("/api/schedule/brief", json={
        "trigger": "opened", "last_said": [],
    }).json()

    assert body["quiet"] is False
    assert body["items"][0]["suggestion"]


def test_a_briefing_never_breaks_the_screen():
    """No model answer is scripted, so the call fails inside the service.

    It must come back quiet and `200`. This sits beside a calendar that has
    to render whatever the model is doing — an error here would take the
    management area down with it.
    """
    app, _ = _build_app([])

    response = _client(app).post("/api/schedule/brief", json={
        "trigger": "opened",
    })

    assert response.status_code == 200
    assert response.json() == {"headline": "", "items": [], "quiet": True}


def test_a_member_cannot_ask_for_a_briefing():
    """A briefing reads drafts and other people's stated reasons."""
    app, _ = _build_app([])
    member = _client(app, role=ROLE_MEMBER)

    assert member.post(
        "/api/schedule/brief", json={"trigger": "opened"}
    ).status_code == 401


def test_briefing_before_the_interview_is_quiet_without_calling_the_model():
    """Nothing to observe: the agent knows neither the shifts nor the people,
    and a briefing built on that would be invented rather than noticed."""
    app, repo = _build_app([])
    repo.profiles = {}

    body = _client(app).post(
        "/api/schedule/brief", json={"trigger": "opened"}
    ).json()

    assert body["quiet"] is True


# -- leaving the app as a file (D17) ---------------------------------------

def test_a_period_downloads_as_a_workbook():
    app, _ = _build_app([_generation([
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-17",
         "reason": "דנה מוסמכת לבוקר"},
    ])])
    client = _client(app)
    schedule = client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()

    response = client.get("/api/schedule/export/%s" % schedule["id"])

    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    # A real xlsx is a zip; anything else means an error page came back 200.
    assert response.content[:2] == b"PK"


def test_a_member_cannot_download_the_workbook():
    """The share link is how the team reads the roster. A file is a copy that
    leaves the app entirely, and handing that out is the manager's call."""
    app, _ = _build_app([_generation([])])
    client = _client(app)
    schedule = client.post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()

    member = _client(app, role=ROLE_MEMBER)
    assert member.get(
        "/api/schedule/export/%s" % schedule["id"]
    ).status_code == 401


def test_one_workspace_cannot_download_anothers_period():
    app, _ = _build_app([_generation([])])
    schedule = _client(app).post("/api/schedule/generate", json={
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
    }).json()

    other = _client(app, team=OTHER_TEAM)
    assert other.get(
        "/api/schedule/export/%s" % schedule["id"]
    ).status_code == 404
