"""What leaves the API when something fails.

Asserted against the real `app.main.app`, not a router mounted on a fresh
FastAPI: these handlers ARE composition-root configuration, and a test app
that registers its own would prove nothing about what ships.

The `AppError` path was always covered indirectly by the router tests. What
was not covered, and is the reason this file exists, is everything else: an
exception nobody anticipated used to leave as Starlette's default 500, whose
body has no `detail` at all. The frontend reads `detail` and fell through to
`שגיאת שרת (500)` — a bare status code, which tells the manager nothing and
told us nothing either, because the traceback was never logged.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from app.common.errors import AgentError, NotFoundError

import app.main as main


_SECRET = "postgresql://pakash:hunter2@db:5432/pakash"


@pytest.fixture(scope="module")
def client():
    app = main.app

    @app.get("/api/_test_unhandled")
    def _unhandled():
        # Shaped like the errors that actually reach here: a driver or pool
        # failure whose text carries a connection string.
        raise RuntimeError(_SECRET)

    @app.get("/api/_test_agent_error")
    def _agent_error():
        raise AgentError("המודל לא זמין")

    @app.get("/api/_test_not_found")
    def _not_found():
        raise NotFoundError("לא נמצא")

    # `raise_server_exceptions=False` so the handler answers instead of the
    # test client re-raising — which is what a real browser sees.
    return TestClient(app, raise_server_exceptions=False)


def test_an_unhandled_error_answers_json_with_a_detail(client):
    """The field the frontend actually reads.

    Without a `detail` the UI can only print the status code, which is the
    exact dead end this handler exists to remove.
    """
    response = client.get("/api/_test_unhandled")
    assert response.status_code == 500
    body = response.json()
    assert body["detail"]
    assert isinstance(body["detail"], str)


def test_an_unhandled_error_never_leaks_the_exception_text(client):
    """`str(exc)` on a database error can carry a connection string, a query
    with employee names in it, or a file path. None of that belongs on a
    manager's screen (backend/CLAUDE.md) — it goes to the log, which is ours.
    """
    response = client.get("/api/_test_unhandled")
    assert _SECRET not in response.text
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


def test_an_unhandled_error_is_traceable_from_screen_to_log(client, caplog):
    """The id on the screen and the id in the log are the same string.

    That correspondence is the whole feature: the manager quotes a short
    number, and it lands on the exact stack rather than on a guess about
    which of the day's 500s they meant.
    """
    with caplog.at_level(logging.ERROR, logger="pakash.api"):
        response = client.get("/api/_test_unhandled")

    error_id = response.json()["error_id"]
    assert error_id and error_id in response.json()["detail"]

    logged = [r for r in caplog.records if error_id in r.getMessage()]
    assert logged, "the error_id shown to the user is not in the log"
    # `_log.exception`, so the stack is attached rather than only the line.
    assert logged[0].exc_info is not None


def test_each_unhandled_error_gets_its_own_id(client):
    """Two failures must be distinguishable. A constant id would make the
    log line unfindable again the moment it happened twice."""
    first = client.get("/api/_test_unhandled").json()["error_id"]
    second = client.get("/api/_test_unhandled").json()["error_id"]
    assert first != second


def test_an_app_error_still_carries_its_own_hebrew_and_status(client):
    """The specific handler keeps winning. `AgentError` is a 502 with the
    sentence the model layer wrote — adding a catch-all must not flatten
    every failure into one anonymous 500."""
    response = client.get("/api/_test_agent_error")
    assert response.status_code == 502
    assert response.json()["detail"] == "המודל לא זמין"
    assert "error_id" not in response.json()


def test_a_not_found_is_not_swallowed_into_a_500(client):
    response = client.get("/api/_test_not_found")
    assert response.status_code == 404
    assert response.json()["detail"] == "לא נמצא"


def test_an_unknown_route_still_answers_404(client):
    """Starlette's own 404, not the catch-all: registering a handler for
    `Exception` must not turn routing failures into server errors."""
    assert client.get("/api/_no_such_route_at_all").status_code == 404
