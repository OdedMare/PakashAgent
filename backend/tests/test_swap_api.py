"""Shift swaps between employees: consent, guards, and who may decide.

Two employees arranging a swap between themselves is the most common real
schedule change there is, and before this feature the only way to express it
was for one of them to submit a constraint and let the manager rediscover
that a replacement was already agreed.

What the tests below hold in place is the line the feature must not cross.
[D14](../../docs/DECISIONS.md) gave employees exactly one write -- a
*request* -- and a swap is a second one of the same kind, not a new power:

- **an offer moves nothing**, and neither does the colleague accepting it;
- **the manager is the sole decider**, and cannot rule on an arrangement the
  counterparty has not accepted;
- **approval goes through the ordinary `OP_SWAP` path**, so a swap the
  employees arranged and one the manager typed produce the same change log;
- **an employee may only offer their own shift**, and only answer an offer
  actually addressed to them.

The last two are what a reviewer would otherwise have to take on trust, and
each is a single assertion away from being false.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies import Guards
from app.api.routers import employee as employee_router
from app.bl.employee_service import EmployeeService
from app.common.errors import AppError
from app.common.sessions import COOKIE_NAME, ROLE_BOSS, ROLE_MEMBER, issue
from tests.test_employee_api import (
    DANA, MORNING, OTHER_TEAM, SECRET, TEAM, YOSSI,
    _FakeIdentities, _FakeSchedules,
)

EVENING = "ערב"

# A published schedule with one shift each for the two employees. Assignment
# ids are what a swap names -- the employee picks two cells off this grid.
SCHEDULE = {
    "id": "sched-1",
    "assignments": [
        {
            "id": "a-dana", "employee": DANA, "shift": MORNING,
            "date": "2026-03-02", "reason": "שיבוץ",
        },
        {
            "id": "a-yossi", "employee": YOSSI, "shift": EVENING,
            "date": "2026-03-03", "reason": "שיבוץ",
        },
    ],
}


@pytest.fixture
def context():
    repository = _FakeIdentities()
    schedules = _FakeSchedules(repository, schedule=SCHEDULE)
    service = EmployeeService(repository, schedules)
    guards = Guards(SECRET)

    app = FastAPI()
    app.include_router(
        employee_router.build_router(service, guards, SECRET, 30)
    )
    app.include_router(employee_router.build_swap_router(service, guards))

    @app.exception_handler(AppError)
    async def handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc)}
        )

    return TestClient(app), repository, schedules


@pytest.fixture
def client(context):
    return context[0]


def _as_employee(client, name, team=TEAM, passcode="1234"):
    """Sign in as an employee, claiming the name the first time.

    Going through claim and login rather than setting a cookie by hand: both
    leave the *server-issued* cookie in place, so every test below runs on
    the same session the product actually issues. Tests switch between the
    two employees repeatedly, so a second visit logs in rather than claiming
    a name that is already taken.
    """
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, issue(SECRET, team, ROLE_MEMBER, 30))
    body = {"employee": name, "passcode": passcode}
    response = client.post("/api/employee/claim", json=body)
    if response.status_code == 409:
        response = client.post("/api/employee/login", json=body)
    assert response.status_code == 200, response.text


def _as_boss(client, team=TEAM):
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, issue(SECRET, team, ROLE_BOSS, 30))


def _offer(client, reason="חתונה"):
    """Dana offers Yossi her morning for his evening."""
    return client.post("/api/employee/swaps", json={
        "assignment_id": "a-dana",
        "counterparty": YOSSI,
        "counterparty_assignment_id": "a-yossi",
        "reason": reason,
    })


def _agreed_swap(client):
    """Walk an offer to the state the manager rules on: both agreed."""
    _as_employee(client, DANA)
    swap_id = _offer(client).json()["id"]
    _as_employee(client, YOSSI, passcode="5678")
    client.post(
        "/api/employee/swaps/%s/answer" % swap_id, json={"agreed": True}
    )
    return swap_id


# --- an offer is inert ------------------------------------------------------

def test_an_offer_awaits_the_colleague_and_moves_nothing(context):
    client, _, schedules = context
    _as_employee(client, DANA)

    response = _offer(client)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "awaiting_counterparty"
    # The whole promise of the feature: proposing is not scheduling.
    assert schedules.applied == []


def test_agreeing_still_moves_nothing(context):
    client, _, schedules = context
    swap_id = _agreed_swap(client)

    _as_employee(client, DANA)
    mine = [
        row for row in client.get("/api/employee/swaps").json()
        if row["id"] == swap_id
    ]
    # Two employees agreeing between themselves is consent, not approval.
    assert mine[0]["status"] == "pending"
    assert schedules.applied == []


def test_a_declined_offer_ends_and_is_not_the_managers_problem(context):
    client, _, _ = context
    _as_employee(client, DANA)
    swap_id = _offer(client).json()["id"]

    _as_employee(client, YOSSI, passcode="5678")
    response = client.post(
        "/api/employee/swaps/%s/answer" % swap_id, json={"agreed": False}
    )

    assert response.json()["status"] == "declined"
    _as_boss(client)
    # `declined` is the counterparty's refusal and never reaches the inbox --
    # distinct from the manager's `rejected`, which is the point of keeping
    # the two statuses apart.
    assert client.get("/api/schedule/swaps/pending").json() == []


# --- who may act ------------------------------------------------------------

def test_an_employee_can_only_offer_their_own_shift(context):
    client, _, _ = context
    _as_employee(client, YOSSI, passcode="5678")

    # Yossi offering Dana's morning away, naming her as the counterparty.
    response = client.post("/api/employee/swaps", json={
        "assignment_id": "a-dana",
        "counterparty": DANA,
        "counterparty_assignment_id": "a-dana",
        "reason": "",
    })

    assert response.status_code == 401


def test_the_named_shift_must_belong_to_the_named_colleague(context):
    client, _, _ = context
    _as_employee(client, DANA)

    # Dana's own shift offered as though it were Yossi's half of the trade.
    response = client.post("/api/employee/swaps", json={
        "assignment_id": "a-dana",
        "counterparty": YOSSI,
        "counterparty_assignment_id": "a-dana",
        "reason": "",
    })

    assert response.status_code == 502


def test_only_the_counterparty_answers_an_offer(context):
    client, _, _ = context
    _as_employee(client, DANA)
    swap_id = _offer(client).json()["id"]

    # Dana accepting her own proposal would be consent from the one person
    # whose consent the row already records.
    response = client.post(
        "/api/employee/swaps/%s/answer" % swap_id, json={"agreed": True}
    )

    assert response.status_code == 401


def test_an_employee_cannot_approve_a_swap(context):
    client, _, schedules = context
    swap_id = _agreed_swap(client)

    _as_employee(client, DANA)
    response = client.post(
        "/api/schedule/swaps/%s/approve" % swap_id, json={"reason": "בסדר"}
    )

    assert response.status_code in (401, 403)
    assert schedules.applied == []


def test_a_swap_is_invisible_to_another_workspace(context):
    client, _, _ = context
    _as_employee(client, DANA)
    swap_id = _offer(client).json()["id"]

    _as_boss(client, team=OTHER_TEAM)
    response = client.post(
        "/api/schedule/swaps/%s/reject" % swap_id, json={"reason": "לא"}
    )

    # A cross-team miss is a 404 and never a distinct "wrong team", or the
    # endpoint becomes an oracle for rows in workspaces the caller cannot see.
    assert response.status_code == 404


# --- the manager decides ----------------------------------------------------

def test_the_manager_cannot_rule_before_the_colleague_agrees(context):
    client, _, schedules = context
    _as_employee(client, DANA)
    swap_id = _offer(client).json()["id"]

    _as_boss(client)
    response = client.post(
        "/api/schedule/swaps/%s/approve" % swap_id, json={"reason": "בסדר"}
    )

    # The guard is the status, not the UI that usually hides the button.
    assert response.status_code == 409
    assert schedules.applied == []


def test_approval_performs_the_swap_through_the_ordinary_path(context):
    client, _, schedules = context
    swap_id = _agreed_swap(client)

    _as_boss(client)
    response = client.post(
        "/api/schedule/swaps/%s/approve" % swap_id,
        json={"reason": "שניהם מסכימים והכיסוי נשמר"},
    )

    assert response.status_code == 200, response.text
    assert len(schedules.applied) == 1
    call = schedules.applied[0]
    operation = call["operations"][0]
    # The same OP_SWAP a manager-typed swap produces, so the change log
    # records one `swapped` event rather than a second kind of change.
    assert operation["action"] == "swap"
    assert operation["employee"] == DANA
    assert operation["with_employee"] == YOSSI
    assert operation["date"] == "2026-03-02"
    assert operation["with_date"] == "2026-03-03"
    # The manager's own reason (D8), not the employees'.
    assert call["reason"] == "שניהם מסכימים והכיסוי נשמר"
    # And the agent's half states provenance rather than inventing a
    # justification nobody made.
    assert DANA in call["agent_reason"] and YOSSI in call["agent_reason"]


def test_approving_without_a_reason_is_refused(context):
    client, _, schedules = context
    swap_id = _agreed_swap(client)

    _as_boss(client)
    response = client.post(
        "/api/schedule/swaps/%s/approve" % swap_id, json={"reason": "  "}
    )

    # D8 does not exempt a change for having been suggested by the people it
    # affects: this one moves two assignments.
    assert response.status_code == 502
    assert schedules.applied == []


def test_rejecting_requires_a_reason_and_moves_nothing(context):
    client, repository, schedules = context
    swap_id = _agreed_swap(client)
    _as_boss(client)

    assert client.post(
        "/api/schedule/swaps/%s/reject" % swap_id, json={"reason": ""}
    ).status_code == 502

    response = client.post(
        "/api/schedule/swaps/%s/reject" % swap_id,
        json={"reason": "אין מי שיכסה את הערב"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["swap"]["status"] == "rejected"
    assert schedules.applied == []
    # Both employees read the refusal, so it lands in the log naming both.
    logged = [
        row for row in repository.changes if row["action"] == "swap_rejected"
    ]
    assert logged and logged[0]["replaced_employee"] == YOSSI


# --- what each side sees ----------------------------------------------------

def test_both_sides_see_the_swap_labelled_with_their_own_role(context):
    client, _, _ = context
    _as_employee(client, DANA)
    _offer(client)

    dana = client.get("/api/employee/swaps").json()[0]
    _as_employee(client, YOSSI, passcode="5678")
    yossi = client.get("/api/employee/swaps").json()[0]

    # One row, two readers, two different questions -- decided here rather
    # than by comparing names in three components.
    assert dana["is_requester"] and not dana["is_counterparty"]
    assert yossi["is_counterparty"] and not yossi["is_requester"]


def test_only_the_colleague_sees_it_as_waiting_on_them(context):
    client, _, _ = context
    _as_employee(client, DANA)
    _offer(client)

    assert client.get("/api/employee/swaps/incoming").json() == []
    _as_employee(client, YOSSI, passcode="5678")
    incoming = client.get("/api/employee/swaps/incoming").json()

    # The badge means "somebody is waiting on you", which is never true of
    # the person who did the asking.
    assert len(incoming) == 1


def test_the_requester_may_take_an_offer_back(context):
    client, _, _ = context
    _as_employee(client, DANA)
    swap_id = _offer(client).json()["id"]

    response = client.post("/api/employee/swaps/%s/withdraw" % swap_id)

    assert response.json()["status"] == "withdrawn"
    _as_employee(client, YOSSI, passcode="5678")
    # Withdrawn offers leave the colleague's queue.
    assert client.get("/api/employee/swaps/incoming").json() == []


def test_a_repeated_offer_is_refused_rather_than_superseding(context):
    client, _, _ = context
    _as_employee(client, DANA)
    _offer(client)

    response = _offer(client)

    # Unlike a constraint, which restated means the same fact, a second offer
    # would displace one the colleague may already be looking at.
    assert response.status_code == 409


def test_nobody_can_swap_with_themselves(context):
    client, _, _ = context
    _as_employee(client, DANA)

    response = client.post("/api/employee/swaps", json={
        "assignment_id": "a-dana",
        "counterparty": DANA,
        "counterparty_assignment_id": "a-dana",
        "reason": "",
    })

    assert response.status_code == 502
