"""The login throttle and the live signals, shared through PostgreSQL."""

import os
import threading
import time
import uuid
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from app.common.config import Settings
from app.common.errors import AuthError, TooManyAttemptsError
from app.common.throttle import LoginThrottle
from app.dal import database as postgres
from app.dal.notify import PostgresSignals
from app.dal.repository import Repository

pytestmark = pytest.mark.skipif(
    not os.getenv("CHAT_TEST_DSN"), reason="requires a scratch PostgreSQL database"
)


@pytest.fixture
def repo():
    dsn = os.environ["CHAT_TEST_DSN"]
    schema = "shared_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    settings = Settings(_env_file=None, database_url=dsn, database_schema=schema,
                        database_host="", database_user="", database_password="",
                        database_name="", database_port=None)
    repository = Repository(SimpleNamespace(get=lambda: settings))
    try:
        repository.initialize()
        yield repository
    finally:
        postgres.close_pool()
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _wrong():
    raise AuthError("הסיסמה שגויה")


def test_a_lock_set_by_one_process_holds_in_another(repo):
    first, second = LoginThrottle(limit=3, shared=repo), LoginThrottle(limit=3, shared=repo)
    for throttle in (first, second, first):
        with pytest.raises(AuthError):
            throttle.attempt("boss:team", _wrong)

    with pytest.raises(TooManyAttemptsError):
        second.attempt("boss:team", lambda: "ok")
    assert 0 < repo.throttle_locked_for("boss:team") <= 15 * 60


def test_a_right_guess_starts_the_count_over(repo):
    throttle = LoginThrottle(limit=3, shared=repo)
    for _ in range(2):
        with pytest.raises(AuthError):
            throttle.attempt("employee:דנה", _wrong)
    assert throttle.attempt("employee:דנה", lambda: "ok") == "ok"
    for _ in range(2):
        with pytest.raises(AuthError):
            throttle.attempt("employee:דנה", _wrong)
    assert repo.throttle_locked_for("employee:דנה") == 0


def test_a_signal_published_by_one_process_reaches_a_listener(repo):
    bus = PostgresSignals(repo._store)
    heard, running = [], [True]
    listener = threading.Thread(
        target=bus.listen, args=(lambda team, kind: heard.append((team, kind)), lambda: running[0]),
        daemon=True)
    listener.start()
    try:
        deadline = time.monotonic() + 10
        while not heard and time.monotonic() < deadline:
            bus.publish("team-a", "requests")
            time.sleep(0.2)
    finally:
        running[0] = False
        listener.join(5)
    assert ("team-a", "requests") in heard
