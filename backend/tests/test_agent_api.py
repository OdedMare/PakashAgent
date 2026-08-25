"""The HTTP contract for asking, simulating, and remembering.

Reuses the fake repository from `test_schedule_api.py` rather than building a
second one — a divergent fake is how two test files start disagreeing about
what the database does.

Four things here are the point of the feature and are asserted directly:

- **A member cannot reach any of it.** Asking, simulating and preferences are
  all `guards.boss()`, so a member's cookie is refused whichever URL it is
  aimed at (D5/D14).
- **Simulating persists nothing.** The stored schedule is byte-identical
  after a simulation that reports a large change.
- **A mutation still requires confirmation.** Nothing on the answering or
  simulating path writes; applying still demands the manager's reason (D8).
- **One workspace cannot reach another's**, even holding its id (D10).
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
from app.dal.repository.schedules import (
    PREFERENCE_ACTIVE,
    PREFERENCE_SUGGESTED,
)

from tests.test_schedule_api import (
    EVENING,
    MORNING,
    OTHER_TEAM,
    SECRET,
    TEAM,
    _FakeScheduleRepo,
    _ScriptedLlm,
)

DANA = "דנה"
YOSSI = "יוסי"


class _RepoWithPreferences(_FakeScheduleRepo):
    """The schedule fake plus the preference table.

    Subclassed rather than copied so the schedule half can never drift from
    what the other API tests exercise.
    """

    def __init__(self):
        super().__init__()
        self.preference_rows = []

    def create_preference(self, team_id, text, kind="general", subject="",
                          evidence="", status=PREFERENCE_ACTIVE,
                          source="manager"):
        row = {
            "id": self._id("pref"), "team_id": team_id, "kind": kind,
            "subject": subject, "text": text, "evidence": evidence,
            "status": status, "source": source,
        }
        self.preference_rows.append(row)
        return dict(row)

    def get_preference(self, row_id, team_id):
        for row in self.preference_rows:
            if row["id"] == row_id and row["team_id"] == team_id:
                return dict(row)
        raise NotFoundError("ההעדפה לא נמצאה")

    def preferences(self, team_id, status=None):
        rows = [r for r in self.preference_rows if r["team_id"] == team_id]
        if status:
            rows = [r for r in rows if r["status"] == status]
        return [dict(row) for row in rows]

    def update_preference(self, row_id, team_id, text=None, status=None):
        self.get_preference(row_id, team_id)
        for row in self.preference_rows:
            if row["id"] == row_id and row["team_id"] == team_id:
                if text is not None:
                    row["text"] = text
                if status is not None:
                    row["status"] = status
                return dict(row)
        raise NotFoundError("ההעדפה לא נמצאה")

    def delete_preference(self, row_id, team_id):
        self.preference_rows = [
            row for row in self.preference_rows
            if not (row["id"] == row_id and row["team_id"] == team_id)
        ]


class _NoModel:
    """No model configured. Every new route must still answer."""

    def complete_json(self, *args, **kwargs):
        from app.common.errors import AgentError
        raise AgentError("לא הוגדר מפתח API או שרת תואם OpenAI")


def _build_app(llm=None):
    repository = _RepoWithPreferences()
    guards = Guards(SECRET)
    app = FastAPI()
    app.include_router(
        schedules.build_router(
            ScheduleService(repository, llm or _NoModel()), guards
        )
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


def _seed(repo, team_id=TEAM, assignments=None):
    """A two-day period with both shifts on each day."""
    schedule = repo.create_schedule(team_id, "2026-08-17", "2026-08-18")
    repo.replace_slots(schedule["id"], team_id, [
        {"shift_name": shift, "slot_date": date,
         "start_time": "07:00" if shift == MORNING else "15:00",
         "end_time": "15:00" if shift == MORNING else "23:00",
         "headcount": 1, "is_on_call": False}
        for date in ("2026-08-17", "2026-08-18")
        for shift in (MORNING, EVENING)
    ])
    for item in assignments or []:
        slot = repo.find_slot(
            schedule["id"], team_id, item["shift"], item["date"]
        )
        repo.add_assignment(
            schedule["id"], team_id, slot["id"], item["employee"], "בדיקה",
        )
    return repo.get_schedule(schedule["id"], team_id)


# -- asking ----------------------------------------------------------------


def test_asking_answers_with_no_model_configured():
    """The product's promise, at the HTTP boundary."""
    app, repo = _build_app()
    _seed(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    response = _client(app).post(
        "/api/schedule/ask", json={"request": "מה חסר בסידור"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["understood"] is True
    assert body["used_model"] is False
    assert body["answer"]


def test_the_agent_can_talk_before_any_schedule_exists():
    app, _ = _build_app()

    response = _client(app).post(
        "/api/schedule/ask", json={"request": "מה חסר בסידור"},
    )

    assert response.status_code == 200
    assert "אין סידור" in response.json()["answer"]


def test_an_answer_carries_no_operations():
    """There is no field here `apply` could read (the D15 property)."""
    app, repo = _build_app()
    _seed(repo)
    body = _client(app).post(
        "/api/schedule/ask", json={"request": "מה חסר בסידור"},
    ).json()
    assert "operations" not in body


def test_an_answer_says_which_tools_it_ran():
    """Transparency is the requirement, not debugging output."""
    app, repo = _build_app()
    _seed(repo)
    body = _client(app).post(
        "/api/schedule/ask", json={"request": "מה חסר בסידור"},
    ).json()
    assert body["steps"]
    assert body["steps"][0]["tool"] == "coverage_gaps"


def test_asking_changes_nothing_in_the_schedule():
    app, repo = _build_app()
    schedule = _seed(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    before = repo.get_schedule(schedule["id"], TEAM)
    _client(app).post(
        "/api/schedule/ask",
        json={"request": "מי יכול להחליף את דנה ביום שני"},
    )
    assert repo.get_schedule(schedule["id"], TEAM) == before
    assert repo.changes == []


def test_a_member_cannot_ask():
    """The answering path reads drafts and stated reasons — boss only."""
    app, repo = _build_app()
    _seed(repo)
    response = _client(app, role=ROLE_MEMBER).post(
        "/api/schedule/ask", json={"request": "מה חסר בסידור"},
    )
    assert response.status_code == 401


def test_an_empty_question_is_refused_by_the_contract():
    app, repo = _build_app()
    _seed(repo)
    response = _client(app).post("/api/schedule/ask", json={"request": ""})
    assert response.status_code == 422


# -- tools directly --------------------------------------------------------


def test_a_tool_can_be_run_directly():
    app, repo = _build_app()
    _seed(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    body = _client(app).post("/api/schedule/tool", json={
        "tool": "employee_state", "arguments": {"employee": DANA},
    }).json()
    assert body["ok"] and body["found"]
    assert body["hours"] == 8.0


def test_an_unknown_tool_is_an_answer_not_a_500():
    app, repo = _build_app()
    _seed(repo)
    response = _client(app).post("/api/schedule/tool", json={
        "tool": "drop_database", "arguments": {},
    })
    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_a_member_cannot_run_a_tool():
    app, repo = _build_app()
    _seed(repo)
    response = _client(app, role=ROLE_MEMBER).post(
        "/api/schedule/tool",
        json={"tool": "coverage_gaps", "arguments": {}},
    )
    assert response.status_code == 401


def test_a_tool_cannot_reach_another_workspace():
    """Naming a team is not reaching one (D10)."""
    app, repo = _build_app()
    theirs = _seed(repo, team_id=OTHER_TEAM)
    body = _client(app).post("/api/schedule/tool", json={
        "tool": "read_period", "arguments": {"schedule_id": theirs["id"]},
    }).json()
    assert body["found"] is False


# -- simulating ------------------------------------------------------------


def test_a_simulation_persists_nothing():
    """The property the whole flow rests on."""
    app, repo = _build_app()
    schedule = _seed(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    before = repo.get_schedule(schedule["id"], TEAM)

    response = _client(app).post("/api/schedule/simulate", json={
        "operations": [
            {"action": "remove", "employee": DANA, "shift": MORNING,
             "date": "2026-08-17", "reason": "בדיקה"},
            {"action": "assign", "employee": YOSSI, "shift": MORNING,
             "date": "2026-08-17", "reason": "בדיקה"},
        ],
    })
    assert response.status_code == 200
    assert response.json()["applied"] is True
    # Nothing moved, and no change-log row was written either.
    assert repo.get_schedule(schedule["id"], TEAM) == before
    assert repo.changes == []


def test_a_simulation_says_it_is_a_simulation():
    """The field the UI colours off, so it can never render as confirmed."""
    app, repo = _build_app()
    _seed(repo)
    body = _client(app).post("/api/schedule/simulate", json={
        "operations": [{"action": "assign", "employee": YOSSI,
                        "shift": EVENING, "date": "2026-08-17",
                        "reason": "בדיקה"}],
    }).json()
    assert body["simulated"] is True


def test_a_simulation_reports_its_impact():
    app, repo = _build_app()
    _seed(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    body = _client(app).post("/api/schedule/simulate", json={
        "operations": [
            {"action": "remove", "employee": DANA, "shift": MORNING,
             "date": "2026-08-17", "reason": "בדיקה"},
            {"action": "assign", "employee": YOSSI, "shift": MORNING,
             "date": "2026-08-17", "reason": "בדיקה"},
        ],
    }).json()
    assert set(body["affected"]) == {DANA, YOSSI}
    by_name = {row["employee"]: row for row in body["workload"]}
    assert by_name[DANA]["delta"] == -8.0
    assert by_name[YOSSI]["delta"] == 8.0
    assert body["coverage"]["delta"] == 0


def test_a_simulated_operation_that_cannot_apply_is_reported():
    app, repo = _build_app()
    _seed(repo)
    body = _client(app).post("/api/schedule/simulate", json={
        "operations": [{"action": "assign", "employee": YOSSI,
                        "shift": EVENING, "date": "2027-01-01",
                        "reason": "בדיקה"}],
    }).json()
    assert body["applied"] is False
    assert body["skipped"] and body["skipped"][0]["why"]


def test_a_member_cannot_simulate():
    app, repo = _build_app()
    _seed(repo)
    response = _client(app, role=ROLE_MEMBER).post(
        "/api/schedule/simulate", json={"operations": []},
    )
    assert response.status_code == 401


def test_simulating_another_workspace_period_is_not_found():
    app, repo = _build_app()
    theirs = _seed(repo, team_id=OTHER_TEAM)
    response = _client(app).post("/api/schedule/simulate", json={
        "operations": [], "schedule_id": theirs["id"],
    })
    assert response.status_code == 404


# -- approval is still required --------------------------------------------


def test_approving_a_simulation_goes_through_apply_with_a_reason():
    """There is no shortcut from a simulation to a write (D8)."""
    app, repo = _build_app()
    schedule = _seed(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    operations = [
        {"action": "remove", "employee": DANA, "shift": MORNING,
         "date": "2026-08-17", "reason": "בדיקה"},
    ]
    client = _client(app)

    # Simulating changes nothing.
    client.post("/api/schedule/simulate", json={"operations": operations})
    assert len(repo.get_schedule(schedule["id"], TEAM)["assignments"]) == 1

    # Applying without a reason is refused.
    refused = client.post("/api/schedule/apply", json={
        "schedule_id": schedule["id"], "operations": operations, "reason": "",
    })
    assert refused.status_code == 422

    # With one, it lands and is logged.
    applied = client.post("/api/schedule/apply", json={
        "schedule_id": schedule["id"], "operations": operations,
        "reason": "דנה חולה", "agent_reason": "אין תחליף זמין",
    })
    assert applied.status_code == 200
    assert applied.json()["assignments"] == []
    entry = repo.changes[-1]
    assert entry["action"] == "removed"
    assert entry["reason"] == "דנה חולה"
    # The operation's own reason wins over the proposal-level one when it
    # carries one -- `_apply_one` prefers the per-operation sentence, which
    # is the more specific of the two.
    assert entry["agent_reason"] == "בדיקה"


# -- preferences -----------------------------------------------------------


def test_a_preference_is_stored_and_listed():
    app, repo = _build_app()
    created = _client(app).post("/api/schedule/preferences", json={
        "text": "עדיף לשאול את יוסי לפני רון לסופ״ש",
        "kind": "staffing",
    })
    assert created.status_code == 200
    assert created.json()["status"] == PREFERENCE_ACTIVE

    listed = _client(app).get("/api/schedule/preferences/list")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_a_suggested_preference_is_inert_until_approved():
    """One decision is a decision; it becomes a rule when the manager says so."""
    app, repo = _build_app()
    created = _client(app).post("/api/schedule/preferences", json={
        "text": "נראה שאתה מעדיף בקרים למאיה", "suggested": True,
    }).json()
    assert created["status"] == PREFERENCE_SUGGESTED

    # `ask` reads only active ones, so a suggestion changes nothing.
    active = _client(app).get(
        "/api/schedule/preferences/list", params={"status": PREFERENCE_ACTIVE},
    ).json()
    assert active == []

    approved = _client(app).patch(
        "/api/schedule/preferences/%s" % created["id"],
        json={"status": PREFERENCE_ACTIVE},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == PREFERENCE_ACTIVE


def test_a_preference_can_be_reworded():
    """A stored preference the manager cannot edit is a rule they never agreed to."""
    app, repo = _build_app()
    created = _client(app).post("/api/schedule/preferences", json={
        "text": "מקור",
    }).json()
    updated = _client(app).patch(
        "/api/schedule/preferences/%s" % created["id"],
        json={"text": "מתוקן"},
    )
    assert updated.json()["text"] == "מתוקן"


def test_a_preference_can_be_deleted():
    app, repo = _build_app()
    created = _client(app).post("/api/schedule/preferences", json={
        "text": "טעות",
    }).json()
    assert _client(app).delete(
        "/api/schedule/preferences/%s" % created["id"]
    ).status_code == 200
    assert _client(app).get("/api/schedule/preferences/list").json() == []


def test_a_member_cannot_read_or_write_preferences():
    app, repo = _build_app()
    member = _client(app, role=ROLE_MEMBER)
    assert member.get("/api/schedule/preferences/list").status_code == 401
    assert member.post(
        "/api/schedule/preferences", json={"text": "משהו"},
    ).status_code == 401


def test_one_workspace_cannot_read_another_preferences():
    app, repo = _build_app()
    _client(app, team=OTHER_TEAM).post(
        "/api/schedule/preferences", json={"text": "של הצוות השני"},
    )
    assert _client(app).get("/api/schedule/preferences/list").json() == []


def test_one_workspace_cannot_edit_another_preference():
    app, repo = _build_app()
    theirs = _client(app, team=OTHER_TEAM).post(
        "/api/schedule/preferences", json={"text": "שלהם"},
    ).json()
    response = _client(app).patch(
        "/api/schedule/preferences/%s" % theirs["id"], json={"text": "שלי"},
    )
    assert response.status_code == 404


# -- route ordering --------------------------------------------------------


@pytest.mark.parametrize("path", [
    "/api/schedule/preferences/list",
    "/api/schedule/constraints/list",
    "/api/schedule/history/list",
])
def test_literal_paths_are_not_read_as_schedule_ids(path):
    """`/{schedule_id}` is declared last; these must not fall into it."""
    app, repo = _build_app()
    _seed(repo)
    assert _client(app).get(path).status_code == 200


# -- clarification, at the HTTP boundary -----------------------------------
#
# The contract the frontend depends on: a question comes back with the
# request it is waiting on, the manager's answer is sent back beside it, and
# nothing is written in between.


def _asking(reply, **extra):
    """A change turn that asks rather than proposes."""
    answer = {
        "reply": reply, "needs_reason": False, "needs_input": True,
        "agent_reason": "", "operations": [], "constraints": [],
        "profile_operations": [],
    }
    answer.update(extra)
    return answer


def _proposing(operations, **extra):
    answer = {
        "reply": "הצעה", "needs_reason": False, "needs_input": False,
        "agent_reason": "הכי פנוי ומוסמך", "operations": operations,
        "constraints": [], "profile_operations": [],
    }
    answer.update(extra)
    return answer


def test_an_ambiguous_change_asks_and_writes_nothing():
    """The acceptance criterion, end to end.

    The model is scripted to be confident — it names a shift and a date and
    sets `needs_input` false. Code holds it anyway, because "דניאל" is two
    people here, and the stored schedule is unchanged afterwards.
    """
    llm = _ScriptedLlm([_proposing([
        {"action": "assign", "employee": "דניאל", "shift": MORNING,
         "date": "2026-08-17", "reason": "פנוי"},
    ])])
    app, repo = _build_app(llm)
    schedule = _seed(repo)
    # Two people who both answer to "דניאל" — the case a roster with one of
    # each name cannot produce.
    repo.profiles[TEAM] = dict(
        repo.profiles[TEAM],
        employees=[{"name": "דניאל כהן"}, {"name": "דניאל לוי"}],
    )
    before = repo.get_schedule(schedule["id"], TEAM)

    body = _client(app).post("/api/schedule/propose", json={
        "request": "תשבץ את דניאל", "reason": "כיסוי",
    }).json()

    assert body["needs_input"] is True
    assert body["operations"] == []
    assert body["pending_request"] == "תשבץ את דניאל"
    assert repo.get_schedule(schedule["id"], TEAM) == before


def test_a_change_naming_nobody_on_the_roster_asks_too():
    """The other half of the same gate: a name the workplace does not have.

    Separated from the ambiguous case because they are different failures
    asked about differently — "which one" needs candidates to offer, "who is
    that" has none.
    """
    llm = _ScriptedLlm([_proposing([
        {"action": "assign", "employee": "אבישי", "shift": MORNING,
         "date": "2026-08-17", "reason": "פנוי"},
    ])])
    app, repo = _build_app(llm)
    schedule = _seed(repo)
    before = repo.get_schedule(schedule["id"], TEAM)

    body = _client(app).post("/api/schedule/propose", json={
        "request": "תשבץ את אבישי", "reason": "כיסוי",
    }).json()

    assert body["needs_input"] is True
    assert body["operations"] == []
    assert repo.get_schedule(schedule["id"], TEAM) == before


def test_the_clarification_resumes_the_original_request():
    """The manager answers the question, not the whole sentence again."""
    llm = _ScriptedLlm([_proposing([
        {"action": "assign", "employee": DANA, "shift": EVENING,
         "date": "2026-08-17", "reason": "פנויה"},
    ])])
    app, repo = _build_app(llm)
    _seed(repo)

    body = _client(app).post("/api/schedule/propose", json={
        "request": "צהריים",
        "pending_request": "תשבץ את דנה",
        "reason": "כיסוי",
    }).json()

    assert body["needs_input"] is False
    assert len(body["operations"]) == 1
    # Nothing left waiting, so the next sentence starts clean.
    assert body["pending_request"] == ""
    # And both halves reached the model.
    sent = llm.calls[0]["user"]
    assert "תשבץ את דנה" in sent
    assert "צהריים" in sent


def test_an_answered_question_is_not_asked_again():
    """The infinite-loop guard, at the boundary that would show it.

    Two turns: the first asks which shift, the second is scripted to propose.
    What is asserted is that the second turn *was given* what it already
    asked and what came back — a model that cannot see either is a model with
    no way to avoid repeating itself.
    """
    llm = _ScriptedLlm([
        _asking("לאיזו משמרת לשבץ את דנה — בוקר או צהריים?"),
        _proposing([
            {"action": "assign", "employee": DANA, "shift": EVENING,
             "date": "2026-08-17", "reason": "פנויה"},
        ]),
    ])
    app, repo = _build_app(llm)
    _seed(repo)
    client = _client(app)

    first = client.post("/api/schedule/propose", json={
        "request": "תשבץ את דנה", "reason": "כיסוי",
    }).json()
    assert first["needs_input"] is True

    second = client.post("/api/schedule/propose", json={
        "request": "צהריים",
        "pending_request": first["pending_request"],
        "reason": "כיסוי",
    }).json()

    assert second["needs_input"] is False
    assert len(second["operations"]) == 1
    sent = llm.calls[1]["user"]
    assert "asked_last_turn" in sent
    assert "answer_to_that" in sent


def test_a_clear_change_request_never_asks():
    """Existing behaviour, unchanged. The regression that would matter most."""
    llm = _ScriptedLlm([_proposing([
        {"action": "remove", "employee": DANA, "shift": MORNING,
         "date": "2026-08-17", "reason": "מחלה"},
    ])])
    app, repo = _build_app(llm)
    _seed(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])

    body = _client(app).post("/api/schedule/propose", json={
        "request": "תוריד את דנה מהבוקר של ה-17", "reason": "מחלה",
    }).json()

    assert body["needs_input"] is False
    assert body["pending_request"] == ""
    assert len(body["operations"]) == 1


def test_a_question_carries_its_pending_request_back():
    """`/ask` gets the same continuation contract as `/propose`."""
    app, repo = _build_app()
    _seed(repo)

    body = _client(app).post(
        "/api/schedule/ask", json={"request": "בלה בלה בלה"},
    ).json()

    # Nothing was placed, so there is nothing to continue.
    assert body["understood"] is False
    assert body["pending_request"] == ""


def test_a_pending_request_from_another_workspace_cannot_target_this_one():
    """`pending_request` is client-supplied text, so it is content, not authority.

    It reaches the model as part of the sentence and nothing else: it names
    no schedule, selects no row, and cannot widen what this session may
    touch. The team the write would land on still comes from the cookie.
    """
    llm = _ScriptedLlm([_proposing([
        {"action": "assign", "employee": DANA, "shift": MORNING,
         "date": "2026-08-17", "reason": "פנויה"},
    ])])
    app, repo = _build_app(llm)
    _seed(repo)

    body = _client(app).post("/api/schedule/propose", json={
        "request": "בוקר",
        "pending_request": "תשבץ מישהו בצוות אחר",
        "reason": "כיסוי",
    }).json()

    assert body["schedule_id"] == repo.current_schedule(TEAM)["id"]
