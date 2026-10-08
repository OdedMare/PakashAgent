"""The manager's live line: an employee's write wakes the boss's screen.

What is asserted here is what would otherwise be taken on trust:

- a signal reaches only the team it was published for -- a stream is a
  read path, and team scoping is what every read path owes (D10);
- a sync route (a worker thread) can wake an async stream (the event loop);
- the employee routes publish only after the write succeeded;
- the stream is boss-only, like every other route on the manager's router.
"""

import asyncio
import threading

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies.dependencies import Guards
from app.api.routers import employee as employee_router
from app.api.routers.employee.live import stream
from app.bl.employee_service import EmployeeService
from app.common.errors.errors import AppError
from app.common.events import REQUESTS, SWAPS, TeamEvents
from app.common.sessions.sessions import ROLE_EMPLOYEE, ROLE_MEMBER
from tests.test_employee_api import (
    DANA, OTHER_TEAM, SECRET, TEAM, _as, _FakeIdentities, _FakeSchedules,
)


class _Recorder(TeamEvents):
    def __init__(self):
        super().__init__()
        self.published = []

    def publish(self, team_id, kind):
        self.published.append((team_id, kind))
        super().publish(team_id, kind)


def _context():
    repository = _FakeIdentities()
    service = EmployeeService(repository, _FakeSchedules(repository))
    guards = Guards(SECRET)
    events = _Recorder()
    app = FastAPI()
    app.include_router(employee_router.build_router(
        service, guards, SECRET, 30, events=events,
    ))
    app.include_router(
        employee_router.build_manager_router(service, guards, events)
    )

    @app.exception_handler(AppError)
    async def handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc)}
        )

    return TestClient(app), repository, events


# --- the bus ----------------------------------------------------------------

def test_a_signal_reaches_only_its_own_team():
    events = TeamEvents()

    async def scenario():
        with events.subscribe(TEAM) as mine, events.subscribe(OTHER_TEAM) as theirs:
            events.publish(TEAM, REQUESTS)
            await asyncio.sleep(0)
            return mine.qsize(), theirs.qsize()

    assert asyncio.run(scenario()) == (1, 0)


def test_a_worker_thread_wakes_the_event_loop():
    """Sync routes run on a thread pool; the stream waits on the loop."""
    events = TeamEvents()

    async def scenario():
        with events.subscribe(TEAM) as inbox:
            threading.Thread(target=events.publish, args=(TEAM, SWAPS)).start()
            return await asyncio.wait_for(inbox.get(), timeout=2)

    assert asyncio.run(scenario()) == SWAPS


def test_leaving_unsubscribes():
    events = TeamEvents()

    async def scenario():
        with events.subscribe(TEAM):
            assert events.subscriber_count(TEAM) == 1
        return events.subscriber_count(TEAM)

    assert asyncio.run(scenario()) == 0


# --- the stream -------------------------------------------------------------

def test_the_stream_frames_a_signal_and_ends_on_its_own():
    events = TeamEvents()

    async def scenario():
        frames = []
        async for frame in stream(events, TEAM, heartbeat=0.05, lifetime=0.3):
            frames.append(frame)
            if len(frames) == 1:
                events.publish(TEAM, REQUESTS)
        return frames

    frames = asyncio.run(scenario())

    assert frames[0].startswith("retry:")
    assert "event: requests\ndata: {}\n\n" in frames
    assert ": keep-alive\n\n" in frames
    assert events.subscriber_count(TEAM) == 0


def test_the_stream_is_boss_only():
    client, _, _ = _context()
    for role, name in ((ROLE_EMPLOYEE, DANA), (ROLE_MEMBER, None)):
        _as(client, role, name=name)
        assert client.get("/api/schedule/requests/events").status_code == 401


# --- who publishes ----------------------------------------------------------

def test_submitting_a_request_wakes_the_manager():
    client, _, events = _context()
    _as(client, ROLE_EMPLOYEE, name=DANA)

    response = client.post(
        "/api/employee/requests", json={"constraint_date": "2026-03-02"},
    )

    assert response.status_code == 200, response.text
    assert events.published == [(TEAM, REQUESTS)]


def test_withdrawing_a_request_wakes_the_manager():
    client, repository, events = _context()
    row = repository.submit_request(TEAM, DANA, "2026-03-05")
    _as(client, ROLE_EMPLOYEE, name=DANA)

    client.post("/api/employee/requests/%s/withdraw" % row["id"])

    assert events.published == [(TEAM, REQUESTS)]


def test_a_refused_write_wakes_nobody():
    client, repository, events = _context()
    row = repository.submit_request(TEAM, "יוסי", "2026-03-05")
    _as(client, ROLE_EMPLOYEE, name=DANA)

    response = client.post("/api/employee/requests/%s/withdraw" % row["id"])

    assert response.status_code == 401
    assert events.published == []
