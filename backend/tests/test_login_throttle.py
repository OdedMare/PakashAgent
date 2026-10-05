"""Password guessing: the settings lock and the per-account throttle.

The settings routes are process-wide, and anyone can open a workspace and be
its boss -- so a boss session must not be enough to reach them. And every
password check must stop answering after a handful of wrong guesses, or a
six-digit secret falls in minutes.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies.dependencies import Guards
from app.api.routers import settings as settings_router
from app.api.routers import workspace
from app.bl.workspace_service.service import WorkspaceService
from app.common.errors.errors import AppError, AuthError
from app.common.sessions.sessions import COOKIE_NAME, ROLE_BOSS, issue
from app.common.throttle.throttle import LoginThrottle

from tests.test_settings_api import FakeLLM, store  # noqa: F401 -- fixture
from tests.test_workspace_api import _FakeRepo

SECRET = "test-secret"
PASSWORD = "010802"
HEADER = settings_router.PASSWORD_HEADER


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _app(*routers) -> FastAPI:
    app = FastAPI()
    for router in routers:
        app.include_router(router)

    @app.exception_handler(AppError)
    async def handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc)}
        )

    return app


def _boss(app, team="team-1") -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(COOKIE_NAME, issue(SECRET, team, ROLE_BOSS, 1))
    return client


@pytest.fixture
def settings_app(store):  # noqa: F811 -- pytest fixture injection
    return _app(settings_router.build_router(
        store, FakeLLM(), Guards(SECRET), PASSWORD,
        LoginThrottle(limit=3),
    ))


# --- the settings lock ------------------------------------------------------


@pytest.mark.parametrize("method,path", [
    ("get", "/api/settings"),
    ("put", "/api/settings"),
    ("get", "/api/models"),
    ("post", "/api/models"),
])
def test_a_boss_without_the_password_is_refused_everywhere(
    settings_app, method, path
):
    kwargs = {"json": {}} if method in ("put", "post") else {}
    response = getattr(_boss(settings_app), method)(path, **kwargs)

    assert response.status_code == 403


def test_a_wrong_password_is_refused(settings_app):
    response = _boss(settings_app).get(
        "/api/settings", headers={HEADER: "000000"}
    )

    assert response.status_code == 403


def test_the_right_password_opens_the_settings(settings_app):
    response = _boss(settings_app).get(
        "/api/settings", headers={HEADER: PASSWORD}
    )

    assert response.status_code == 200


def test_the_password_does_not_replace_the_boss_session(settings_app):
    anonymous = TestClient(settings_app, raise_server_exceptions=False)

    response = anonymous.get("/api/settings", headers={HEADER: PASSWORD})

    assert response.status_code == 401


def test_an_unset_password_keeps_the_settings_locked(store):  # noqa: F811
    app = _app(settings_router.build_router(store, FakeLLM(), Guards(SECRET)))

    response = _boss(app).get("/api/settings", headers={HEADER: ""})

    assert response.status_code == 403


def test_repeated_wrong_passwords_lock_the_workspace_out(settings_app):
    boss = _boss(settings_app)
    for _ in range(3):
        boss.get("/api/settings", headers={HEADER: "000000"})

    response = boss.get("/api/settings", headers={HEADER: PASSWORD})

    # Locked even with the right password: otherwise the lockout only
    # delays the guess that would have succeeded anyway.
    assert response.status_code == 429


def test_one_workspace_s_lockout_does_not_lock_another(settings_app):
    attacker = _boss(settings_app, team="team-1")
    for _ in range(3):
        attacker.get("/api/settings", headers={HEADER: "000000"})

    response = _boss(settings_app, team="team-2").get(
        "/api/settings", headers={HEADER: PASSWORD}
    )

    assert response.status_code == 200


# --- the throttle itself ----------------------------------------------------


def _wrong():
    raise AuthError("שגוי")


def _fail(throttle, key, times):
    for _ in range(times):
        with pytest.raises(AuthError):
            throttle.attempt(key, _wrong)


def test_the_lockout_expires():
    clock = _Clock()
    throttle = LoginThrottle(limit=2, lockout_seconds=60, clock=clock)
    _fail(throttle, "k", 2)

    clock.now += 61

    assert throttle.attempt("k", lambda: "ok") == "ok"


def test_failures_outside_the_window_do_not_add_up():
    clock = _Clock()
    throttle = LoginThrottle(limit=2, window_seconds=60, clock=clock)
    _fail(throttle, "k", 1)
    clock.now += 61
    _fail(throttle, "k", 1)

    assert throttle.attempt("k", lambda: "ok") == "ok"


def test_a_success_clears_the_count():
    throttle = LoginThrottle(limit=2)
    _fail(throttle, "k", 1)
    throttle.attempt("k", lambda: "ok")
    _fail(throttle, "k", 1)

    assert throttle.attempt("k", lambda: "ok") == "ok"


def test_an_error_that_is_not_a_wrong_password_does_not_count():
    throttle = LoginThrottle(limit=1)

    def broken():
        raise RuntimeError("database down")

    with pytest.raises(RuntimeError):
        throttle.attempt("k", broken)

    assert throttle.attempt("k", lambda: "ok") == "ok"


# --- the boss login ---------------------------------------------------------


def test_the_boss_login_locks_after_repeated_wrong_passwords():
    app = _app(workspace.build_router(
        WorkspaceService(_FakeRepo()), Guards(SECRET), SECRET, 30,
        LoginThrottle(limit=3),
    ))
    client = TestClient(app, raise_server_exceptions=False)
    team = client.post(
        "/api/workspace", json={"name": "צוות", "password": "sod-gadol"}
    ).json()

    statuses = [
        client.post("/api/workspace/login", json={
            "team_id": team["id"], "password": "wrong-one",
        }).status_code
        for _ in range(3)
    ]
    locked = client.post("/api/workspace/login", json={
        "team_id": team["id"], "password": "sod-gadol",
    })

    assert statuses == [401, 401, 401]
    assert locked.status_code == 429
