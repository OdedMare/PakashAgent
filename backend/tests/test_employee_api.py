"""The employee area's HTTP boundary: identity, isolation, and scope.

The isolation tests are the point of the feature, exactly as they are in
`test_workspace_api.py`. [D14](../../docs/DECISIONS.md) gave employees a real
identity and one narrow write, and the risk that arrives with it is an
employee reading or acting as a *colleague*. Every test below asserts a thing
a reviewer would otherwise take on trust:

- the name is taken off the signed cookie, never off the request body;
- an employee cookie cannot reach a manager route no matter the URL;
- a pending request changes nothing until a manager approves it.

The last property is the one that keeps D3 intact: if submitting a constraint
ever moves the audit's arithmetic on its own, `test_a_pending_request_is_not_a
_constraint` fails and D14's central promise has been broken.
"""

import datetime

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies import Guards
from app.api.routers import employee as employee_router
from app.bl.employee_service import EmployeeService
from app.common.errors import AppError, AuthError, ConflictError, NotFoundError
from app.common.sessions import (
    COOKIE_NAME, ROLE_BOSS, ROLE_EMPLOYEE, ROLE_MEMBER, issue,
)
from app.dal.repository.teams import hash_password, verify_password

SECRET = "test-secret"
TEAM = "team-1"
OTHER_TEAM = "team-2"

DANA = "דנה"
YOSSI = "יוסי"
MORNING = "בוקר"

PROFILE = {
    "employees": [{"name": DANA}, {"name": YOSSI}],
    "shifts": [{
        "name": MORNING, "start_time": "07:00", "end_time": "15:00",
        "is_on_call": False, "hour_weight": 1.0,
    }],
}


class _FakeIdentities:
    """Identity and request storage, in memory.

    Mirrors the real repository's *refusals* as well as its writes -- a fake
    that accepts a duplicate claim would make the conflict test pass while
    the production path silently allowed an account takeover.
    """

    def __init__(self):
        self.identities = {}       # (team, employee) -> passcode_hash
        # (team, employee) -> when they last acknowledged their changes.
        # Separate from the hash exactly as the real column is separate from
        # `last_seen_at`: a login is not a reading (D16).
        self.acknowledged = {}
        self.requests = {}         # id -> row
        # Promoted constraints. Named `_constraints` because `availability`
        # is a *method* on the real repository -- a list attribute of that
        # name would shadow it and hide the call the service actually makes.
        self._constraints = []
        self.changes = []
        self._next = 0

    # -- identities --
    def claim_identity(self, team_id, employee, passcode):
        employee = (employee or "").strip()
        if (team_id, employee) in self.identities:
            raise ConflictError("השם הזה כבר משויך. פנו למנהל אם זו טעות")
        self.identities[(team_id, employee)] = hash_password(passcode)
        return {"team_id": team_id, "employee": employee}

    def authenticate_employee(self, team_id, employee, passcode):
        employee = (employee or "").strip()
        stored = self.identities.get((team_id, employee))
        if stored is None or not verify_password(passcode or "", stored):
            raise AuthError("השם או הקוד האישי שגויים")
        return {"team_id": team_id, "employee": employee}

    def claimed_names(self, team_id):
        return [name for (team, name) in self.identities if team == team_id]

    def list_identities(self, team_id):
        return [
            {"employee": name, "created_at": None, "last_seen_at": None}
            for (team, name) in self.identities if team == team_id
        ]

    def find_identity(self, team_id, employee):
        key = (team_id, (employee or "").strip())
        if key not in self.identities:
            return None
        return {
            "team_id": team_id, "employee": key[1],
            "created_at": None, "last_seen_at": None,
            "acknowledged_at": self.acknowledged.get(key),
        }

    def acknowledge(self, team_id, employee):
        key = (team_id, (employee or "").strip())
        if key in self.identities:
            self.acknowledged[key] = datetime.datetime.now(
                datetime.timezone.utc
            )

    def release_identity(self, team_id, employee):
        key = (team_id, (employee or "").strip())
        self.identities.pop(key, None)
        self.acknowledged.pop(key, None)

    # -- requests --
    def submit_request(self, team_id, employee, constraint_date,
                       shift_name="", available=False, reason=""):
        self._next += 1
        row_id = "req-%d" % self._next
        for row in self.requests.values():
            if (row["team_id"] == team_id and row["employee"] == employee
                    and row["constraint_date"] == constraint_date
                    and row["shift_name"] == (shift_name or "")
                    and row["status"] == "pending"):
                row["status"] = "withdrawn"
        self.requests[row_id] = {
            "id": row_id, "team_id": team_id, "employee": employee,
            "constraint_date": constraint_date, "shift_name": shift_name or "",
            "available": available, "reason": reason, "status": "pending",
            "decided_reason": "", "decided_at": None,
        }
        return dict(self.requests[row_id])

    def get_request(self, request_id, team_id):
        row = self.requests.get(request_id)
        if row is None or row["team_id"] != team_id:
            raise NotFoundError("הפריט לא נמצא")
        return dict(row)

    def list_requests(self, team_id, employee=None, status=None):
        return [
            dict(row) for row in self.requests.values()
            if row["team_id"] == team_id
            and (employee is None or row["employee"] == employee)
            and (status is None or row["status"] == status)
        ]

    def decide_request(self, request_id, team_id, status, decided_reason=""):
        row = self.get_request(request_id, team_id)
        if row["status"] != "pending":
            raise ConflictError("הבקשה כבר טופלה")
        self.requests[request_id]["status"] = status
        self.requests[request_id]["decided_reason"] = decided_reason
        return dict(self.requests[request_id])

    def withdraw_request(self, request_id, team_id, employee):
        row = self.get_request(request_id, team_id)
        if row["employee"] != (employee or "").strip():
            raise AuthError("אין הרשאה לבקשה הזו")
        if row["status"] != "pending":
            raise ConflictError("הבקשה כבר טופלה")
        self.requests[request_id]["status"] = "withdrawn"
        return dict(self.requests[request_id])

    # -- the rest of the repository surface the service touches --
    def team_profile(self, team_id):
        return PROFILE if team_id in (TEAM, OTHER_TEAM) else None

    def availability(self, team_id, starts_on=None, ends_on=None,
                     employee=None):
        """Same signature as `ScheduleRepository.availability`."""
        return [
            dict(row) for row in self._constraints
            if row["team_id"] == team_id
            and (employee is None or row["employee"] == employee)
        ]

    def change_log(self, team_id, schedule_id=None, limit=None):
        return [row for row in self.changes if row["team_id"] == team_id]

    def append_change(self, team_id, action, **kwargs):
        row = {"team_id": team_id, "action": action}
        row.update(kwargs)
        self.changes.append(row)
        return row


class _FakeSchedules:
    """Stands in for `ScheduleService`.

    `set_constraint` records what it was asked to write, so the approval test
    can assert the *provenance* -- that an approved submission is stored as
    `employee_reported` (D13) rather than as the manager's own entry.
    """

    def __init__(self, repository, schedule=None):
        self._repository = repository
        self.schedule = schedule
        self.constraints = []

    def current(self, team_id, role="boss"):
        return self.schedule

    def set_constraint(self, team_id, employee, constraint_date,
                       shift_name="", available=False, reason="",
                       source="manager"):
        row = {
            "team_id": team_id, "employee": employee,
            "constraint_date": constraint_date, "shift_name": shift_name,
            "available": available, "reason": reason, "source": source,
        }
        self.constraints.append(row)
        self._repository._constraints.append(row)
        return row


@pytest.fixture
def context():
    repository = _FakeIdentities()
    schedules = _FakeSchedules(repository)
    service = EmployeeService(repository, schedules)
    guards = Guards(SECRET)

    app = FastAPI()
    app.include_router(
        employee_router.build_router(service, guards, SECRET, 30)
    )
    app.include_router(employee_router.build_manager_router(service, guards))

    @app.exception_handler(AppError)
    async def handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc)}
        )

    return TestClient(app), repository, schedules


@pytest.fixture
def client(context):
    return context[0]


def _as(client, role, team=TEAM, name=None):
    """Act as a given role.

    Clears first: a preceding `claim` or `login` left a server-issued cookie
    on the client, and setting a second one without clearing lets the stale
    value win -- which would silently make an isolation test pass while
    testing nothing.
    """
    client.cookies.clear()
    client.cookies.set(
        COOKIE_NAME, issue(SECRET, team, role, 30, employee=name)
    )


def _claim(client, name=DANA, passcode="1234", team=TEAM):
    _as(client, ROLE_MEMBER, team)
    response = client.post(
        "/api/employee/claim", json={"employee": name, "passcode": passcode}
    )
    assert response.status_code == 200, response.text
    return response


# --- claiming an identity ---------------------------------------------------

def test_a_share_link_visitor_can_claim_a_roster_name(client):
    """The upgrade path D14 describes: a member session becomes a personal
    one. The share link still grants read-only on its own."""
    _claim(client)

    assert client.get("/api/employee/me").status_code == 200


def test_claiming_signs_the_employee_in_immediately(client):
    response = _claim(client)

    assert COOKIE_NAME in response.headers["set-cookie"]
    assert client.get("/api/employee/me").json()["employee"] == DANA


def test_a_name_not_on_the_roster_cannot_be_claimed(client):
    """Otherwise the share link is a licence to invent employees, and every
    later join on that name silently matches nothing."""
    _as(client, ROLE_MEMBER)

    response = client.post(
        "/api/employee/claim", json={"employee": "מנהל", "passcode": "1234"}
    )

    # 502, the codebase's `AgentError`. Same status the schedule service
    # already returns for a change submitted without a reason -- matching the
    # established convention rather than introducing a second one.
    assert response.status_code == 502


def test_a_claimed_name_cannot_be_claimed_again(client):
    """A silent rebind would be an account takeover whose only requirement is
    holding the share link."""
    _claim(client)
    _as(client, ROLE_MEMBER)

    response = client.post(
        "/api/employee/claim", json={"employee": DANA, "passcode": "9999"}
    )

    assert response.status_code == 409


def test_an_anonymous_visitor_cannot_claim_anything(client):
    assert client.post(
        "/api/employee/claim", json={"employee": DANA, "passcode": "1234"}
    ).status_code == 401


def test_the_passcode_never_appears_in_a_response(client):
    assert "sod-1234" not in _claim(client, passcode="sod-1234").text


def test_the_roster_does_not_leak_when_people_last_signed_in(client):
    """The claim screen is reachable by anyone holding the link. Last-seen is
    the manager's view, not a stranger's."""
    _claim(client)
    _as(client, ROLE_MEMBER)

    body = client.get("/api/employee/roster").text

    assert "last_seen" not in body


def test_the_roster_marks_which_names_are_taken(client):
    _claim(client)
    _as(client, ROLE_MEMBER)

    names = {row["employee"]: row for row in
             client.get("/api/employee/roster").json()["names"]}

    assert names[DANA]["claimed"] is True
    assert names[YOSSI]["claimed"] is False


# --- logging in -------------------------------------------------------------

def test_the_right_passcode_signs_an_employee_in(client):
    _claim(client, passcode="1234")
    _as(client, ROLE_MEMBER)

    response = client.post(
        "/api/employee/login", json={"employee": DANA, "passcode": "1234"}
    )

    assert response.status_code == 200
    assert client.get("/api/employee/me").json()["employee"] == DANA


def test_a_wrong_passcode_is_refused(client):
    _claim(client, passcode="1234")
    _as(client, ROLE_MEMBER)

    assert client.post(
        "/api/employee/login", json={"employee": DANA, "passcode": "9999"}
    ).status_code == 401


def test_an_unclaimed_name_and_a_wrong_passcode_are_indistinguishable(client):
    """Otherwise the endpoint reports which names are claimed to anyone
    holding the link."""
    _claim(client, name=DANA, passcode="1234")
    _as(client, ROLE_MEMBER)

    wrong_code = client.post(
        "/api/employee/login", json={"employee": DANA, "passcode": "9999"}
    )
    unclaimed = client.post(
        "/api/employee/login", json={"employee": YOSSI, "passcode": "9999"}
    )

    assert wrong_code.status_code == unclaimed.status_code == 401
    assert wrong_code.json() == unclaimed.json()


# --- the identity comes off the cookie, never the body ----------------------

def test_an_employee_cannot_read_a_colleagues_area(client):
    """The core isolation property. There is no parameter to put another
    name in -- `me` is scoped entirely by the signed cookie."""
    _as(client, ROLE_EMPLOYEE, name=DANA)

    assert client.get("/api/employee/me").json()["employee"] == DANA


def test_a_submission_is_filed_under_the_cookies_name(context):
    """A name in the body would let one employee submit as another. There is
    no such field, and this pins that."""
    client, repository, _ = context
    _as(client, ROLE_EMPLOYEE, name=DANA)

    client.post("/api/employee/requests", json={
        "constraint_date": "2026-03-02",
        "reason": "בדיקה",
        # Deliberately sent: the contract must ignore it entirely.
        "employee": YOSSI,
    })

    assert [row["employee"] for row in repository.requests.values()] == [DANA]


def test_an_employee_sees_only_their_own_requests(context):
    client, repository, _ = context
    repository.submit_request(TEAM, YOSSI, "2026-03-05", reason="חתונה")
    _as(client, ROLE_EMPLOYEE, name=DANA)
    client.post("/api/employee/requests", json={"constraint_date": "2026-03-02"})

    rows = client.get("/api/employee/requests").json()

    assert [row["employee"] for row in rows] == [DANA]
    assert "חתונה" not in client.get("/api/employee/requests").text


def test_an_employee_cannot_withdraw_a_colleagues_request(context):
    """Scoped by employee as well as by team: the id alone must not be
    enough."""
    client, repository, _ = context
    row = repository.submit_request(TEAM, YOSSI, "2026-03-05")
    _as(client, ROLE_EMPLOYEE, name=DANA)

    response = client.post("/api/employee/requests/%s/withdraw" % row["id"])

    assert response.status_code == 401
    assert repository.requests[row["id"]]["status"] == "pending"


def test_an_employee_cookie_without_a_name_is_rejected(client):
    """A nameless employee cookie is not a weaker session, it is a broken
    one -- every read it authorizes is scoped by that name."""
    client.cookies.set(COOKIE_NAME, issue(SECRET, TEAM, ROLE_EMPLOYEE, 30))

    assert client.get("/api/employee/me").status_code == 401


def test_a_forged_cookie_cannot_reach_the_personal_area(client):
    client.cookies.set(
        COOKIE_NAME, issue("wrong-secret", TEAM, ROLE_EMPLOYEE, 30, employee=DANA)
    )

    assert client.get("/api/employee/me").status_code == 401


# --- employees still cannot act as managers ---------------------------------

def test_an_employee_cannot_reach_the_managers_request_inbox(client):
    """D14 narrowed D5, it did not remove it. The manager remains the sole
    decider, enforced at the routing layer rather than by convention."""
    _as(client, ROLE_EMPLOYEE, name=DANA)

    assert client.get("/api/schedule/requests/pending").status_code == 401
    assert client.get("/api/schedule/requests/identities").status_code == 401


def test_an_employee_cannot_approve_their_own_request(context):
    """The abuse this feature would otherwise make possible."""
    client, repository, _ = context
    row = repository.submit_request(TEAM, DANA, "2026-03-02")
    _as(client, ROLE_EMPLOYEE, name=DANA)

    response = client.post(
        "/api/schedule/requests/%s/approve" % row["id"], json={"reason": ""}
    )

    assert response.status_code == 401
    assert repository.requests[row["id"]]["status"] == "pending"


def test_a_member_cookie_cannot_reach_the_personal_area(client):
    """A share-link session carries no identity, so there is no personal view
    to serve it (D10 unchanged)."""
    _as(client, ROLE_MEMBER)

    assert client.get("/api/employee/me").status_code == 401


def test_a_boss_cannot_reach_the_employee_area_without_claiming(client):
    """Not a downgrade of the boss -- simply that the personal area is scoped
    by a claimed identity the boss session does not carry."""
    _as(client, ROLE_BOSS)

    assert client.get("/api/employee/me").status_code == 401


# --- tenant isolation -------------------------------------------------------

def test_a_claim_in_one_team_does_not_authenticate_in_another(context):
    client, repository, _ = context
    _claim(client, name=DANA, passcode="1234", team=TEAM)
    _as(client, ROLE_MEMBER, team=OTHER_TEAM)

    assert client.post(
        "/api/employee/login", json={"employee": DANA, "passcode": "1234"}
    ).status_code == 401


def test_a_manager_cannot_decide_another_teams_request(context):
    client, repository, _ = context
    row = repository.submit_request(OTHER_TEAM, DANA, "2026-03-02")
    _as(client, ROLE_BOSS, team=TEAM)

    response = client.post(
        "/api/schedule/requests/%s/reject" % row["id"], json={"reason": "לא"}
    )

    assert response.status_code == 404
    assert repository.requests[row["id"]]["status"] == "pending"


# --- a pending request changes nothing --------------------------------------

def test_a_pending_request_is_not_a_constraint(context):
    """**The central promise of D14.**

    Submitting must be inert: invisible to `bl/audit.py`, absent from
    `availability`, incapable of moving a number. If this fails, an employee
    can change the schedule's arithmetic by asking -- which reverses D3 and
    is precisely what keeping the two tables separate exists to prevent.
    """
    client, repository, schedules = context
    _as(client, ROLE_EMPLOYEE, name=DANA)

    client.post("/api/employee/requests", json={
        "constraint_date": "2026-03-02", "reason": "בדיקה רפואית",
    })

    assert repository.requests, "the request itself should have been stored"
    assert schedules.constraints == []
    assert repository._constraints == []


def test_approval_is_what_writes_the_constraint(context):
    client, repository, schedules = context
    row = repository.submit_request(TEAM, DANA, "2026-03-02", reason="בדיקה")
    _as(client, ROLE_BOSS)

    response = client.post(
        "/api/schedule/requests/%s/approve" % row["id"], json={"reason": ""}
    )

    assert response.status_code == 200
    assert len(schedules.constraints) == 1
    assert schedules.constraints[0]["employee"] == DANA


def test_an_approved_request_is_stored_as_employee_reported(context):
    """Provenance, per D13: "Dana said she cannot do Thursdays" stays a
    distinct fact from "the manager decided Dana is off Thursdays"."""
    client, repository, schedules = context
    row = repository.submit_request(TEAM, DANA, "2026-03-02")
    _as(client, ROLE_BOSS)

    client.post("/api/schedule/requests/%s/approve" % row["id"], json={"reason": ""})

    assert schedules.constraints[0]["source"] == "employee_reported"


def test_a_rejection_requires_a_reason(context):
    """A rejection that says nothing is how a submission channel stops being
    used -- and the manager has the reason in mind at the moment they click,
    which is the only moment it is cheap to capture (the D8 argument)."""
    client, repository, _ = context
    row = repository.submit_request(TEAM, DANA, "2026-03-02")
    _as(client, ROLE_BOSS)

    response = client.post(
        "/api/schedule/requests/%s/reject" % row["id"], json={"reason": ""}
    )

    # `AgentError` -> 502, exactly as `schedule_service` answers a change
    # submitted without the manager's reason (D8).
    assert response.status_code == 502
    assert repository.requests[row["id"]]["status"] == "pending"


def test_a_rejection_reaches_the_employee_with_its_reason(context):
    client, repository, _ = context
    row = repository.submit_request(TEAM, DANA, "2026-03-02")
    _as(client, ROLE_BOSS)
    client.post(
        "/api/schedule/requests/%s/reject" % row["id"],
        json={"reason": "חסר כוח אדם ביום הזה"},
    )

    _as(client, ROLE_EMPLOYEE, name=DANA)
    mine = client.get("/api/employee/requests").json()

    assert mine[0]["status"] == "rejected"
    assert mine[0]["decided_reason"] == "חסר כוח אדם ביום הזה"


def test_a_request_cannot_be_decided_twice(context):
    """Otherwise a rejection could quietly become an approval later with
    nothing recording that it changed."""
    client, repository, _ = context
    row = repository.submit_request(TEAM, DANA, "2026-03-02")
    _as(client, ROLE_BOSS)
    client.post("/api/schedule/requests/%s/approve" % row["id"], json={"reason": ""})

    second = client.post(
        "/api/schedule/requests/%s/reject" % row["id"], json={"reason": "לא"}
    )

    assert second.status_code == 409


def test_resubmitting_replaces_the_earlier_pending_request(context):
    """A person restating a constraint means the same one. Two rows would
    give the manager two identical decisions to make."""
    client, repository, _ = context
    _as(client, ROLE_EMPLOYEE, name=DANA)
    body = {"constraint_date": "2026-03-02", "reason": "ראשון"}
    client.post("/api/employee/requests", json=body)
    client.post("/api/employee/requests", json=dict(body, reason="שני"))

    pending = [row for row in repository.requests.values()
               if row["status"] == "pending"]

    assert len(pending) == 1
    assert pending[0]["reason"] == "שני"


# --- releasing a claim ------------------------------------------------------

def test_a_manager_can_release_a_claim_so_the_name_is_free_again(context):
    """The tool for a departure or a forgotten passcode. Rotating the share
    link does not do this -- they are separate credentials."""
    client, repository, _ = context
    _claim(client, name=DANA)
    _as(client, ROLE_BOSS)

    response = client.post(
        "/api/schedule/requests/identities/release", json={"employee": DANA}
    )

    assert response.status_code == 200
    assert repository.claimed_names(TEAM) == []


def test_an_employee_cannot_release_a_claim(client):
    _as(client, ROLE_EMPLOYEE, name=DANA)

    assert client.post(
        "/api/schedule/requests/identities/release", json={"employee": YOSSI}
    ).status_code == 401
