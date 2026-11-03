"""Writes are noticed at the cursor and told after the commit (D50).

The read cache is only as good as its invalidation, so this asserts the
part that decides it: which statements count as writes, which team they
are charged to, and that nothing is told before the transaction is over.
The PostgreSQL half runs against `CHAT_TEST_DSN` and is skipped without it.
"""

import os
import uuid
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from app.common.config import Settings
from app.dal import database as postgres
from app.dal import write_marks
from app.dal.llm.team_context import model_team


@pytest.mark.parametrize("query", [
    "INSERT INTO assignments (id) VALUES (%s)",
    "  update schedules SET status='published' WHERE id=%s",
    "DELETE FROM availability WHERE id=%s",
    "-- a comment first\nUPDATE team_profiles SET revision=revision+1",
    "WITH gone AS (DELETE FROM assignments RETURNING id) SELECT count(*) FROM gone",
    "CREATE TABLE IF NOT EXISTS x (id int)",
    "TRUNCATE assignments",
])
def test_a_write_is_a_write(query):
    assert write_marks.is_write(query)


@pytest.mark.parametrize("query", [
    "SELECT * FROM schedules WHERE team_id=%s",
    "  select pg_advisory_lock(1)",
    "SELECT pg_notify(%s, %s)",
    "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE",
    "LISTEN pakash",
    "WITH recent AS (SELECT 1) SELECT * FROM recent",
    "",
    # Tables no cached read looks at: marking them would retire every
    # cache on every job claim and every login.
    "UPDATE copilot_jobs SET status='running' WHERE id=%s",
    "INSERT INTO login_attempts (account) VALUES (%s)",
    "UPDATE manager_chat_messages SET payload=%s",
])
def test_a_read_or_an_unwatched_table_is_not(query):
    assert not write_marks.is_write(query)


class _Connection:
    pass


@pytest.fixture
def heard():
    told = []
    write_marks.on_written(lambda teams: told.append(teams))
    yield told
    write_marks.on_written(None)


def test_a_write_is_charged_to_the_team_in_context(heard):
    connection = _Connection()
    with model_team("t1"):
        write_marks.mark(connection, "UPDATE schedules SET status='draft'")
    write_marks.mark(connection, "DELETE FROM complex_duties WHERE id=%s")
    assert heard == []  # nothing until the flush
    write_marks.flush(connection)
    assert heard == [{"t1", ""}]
    write_marks.flush(connection)
    assert heard == [{"t1", ""}]  # told once


def test_a_listener_that_raises_never_fails_the_write():
    write_marks.on_written(lambda teams: 1 / 0)
    try:
        connection = _Connection()
        write_marks.mark(connection, "UPDATE schedules SET status='draft'")
        write_marks.flush(connection)
    finally:
        write_marks.on_written(None)


# --- against PostgreSQL -------------------------------------------------------

needs_postgres = pytest.mark.skipif(
    not os.getenv("CHAT_TEST_DSN"), reason="requires a scratch PostgreSQL database"
)


@pytest.fixture
def store():
    dsn = os.environ["CHAT_TEST_DSN"]
    schema = "marks_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    settings = Settings(_env_file=None, database_url=dsn, database_schema=schema,
                        database_host="", database_user="", database_password="",
                        database_name="", database_port=None)
    store = SimpleNamespace(get=lambda: settings)
    with postgres.single_statement(store) as connection:
        connection.execute("CREATE TABLE notes (id int, team_id text)")
    try:
        yield store
    finally:
        postgres.close_pool()
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@needs_postgres
def test_a_pooled_write_is_told_once_the_connection_is_back(store, heard):
    heard.clear()
    with model_team("t1"):
        with postgres.connect(store) as connection:
            connection.execute("INSERT INTO notes VALUES (1, 't1')")
            connection.commit()
            assert heard == []  # committed, but not yet returned
    assert heard == [{"t1"}]


@needs_postgres
def test_a_read_tells_nothing(store, heard):
    heard.clear()
    with model_team("t1"):
        with postgres.single_statement(store) as connection:
            connection.execute("SELECT * FROM notes").fetchall()
    assert heard == []


@needs_postgres
def test_an_atomic_write_is_told_after_the_whole_transaction(store, heard):
    heard.clear()
    with model_team("t2"):
        with postgres.atomic(store) as connection:
            connection.execute("INSERT INTO notes VALUES (2, 't2')")
            with postgres.single_statement(store) as inner:
                inner.execute("UPDATE notes SET id=3 WHERE id=2")
            assert heard == []
    assert heard == [{"t2"}]


@needs_postgres
def test_a_job_s_write_is_told_at_each_commit(store, heard):
    heard.clear()
    with postgres.connect(store) as job_connection:
        with postgres.bind_job_connection(store, job_connection), model_team("t3"):
            with postgres.single_statement(store) as connection:
                connection.execute("INSERT INTO notes VALUES (4, 't3')")
            # The job keeps its connection; the write is told now, mid-job.
            assert heard == [{"t3"}]


def test_a_listener_s_own_writes_are_not_told_back_to_it():
    told = []

    def listener(teams):
        told.append(teams)
        inner = _Connection()
        write_marks.mark(inner, "UPDATE schedules SET status='draft'")
        write_marks.flush(inner)  # from inside the listener: not re-told

    write_marks.on_written(listener)
    try:
        connection = _Connection()
        write_marks.mark(connection, "UPDATE schedules SET status='draft'")
        write_marks.flush(connection)
    finally:
        write_marks.on_written(None)
    assert told == [{""}]
