"""The durable queue's claim and retention, against a real PostgreSQL.

Skipped without `CHAT_TEST_DSN`, like `test_admin_postgres.py`. Each run gets
a throwaway schema, so it never touches real data.
"""

import os
import uuid
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from app.common.config import Settings
from app.dal import database as postgres
from app.dal.repository import Repository

pytestmark = pytest.mark.skipif(
    not os.getenv("CHAT_TEST_DSN"), reason="requires a scratch PostgreSQL database"
)


@pytest.fixture
def repo():
    dsn = os.environ["CHAT_TEST_DSN"]
    schema = "jobs_test_" + uuid.uuid4().hex[:12]
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


def _sql(repo, query, params=()):
    with postgres.connect(repo._store) as connection:
        connection.execute(query, params)
        connection.commit()


def test_a_queued_job_is_reached_past_a_window_of_running_ones(repo):
    """More live jobs than one claim looks at must not hide a queued one."""
    team = repo.create_team("משמרת א", "sod-gadol")
    for index in range(60):
        repo.enqueue_copilot_job(team["id"], "busy:%d" % index, "scan", {})
    _sql(repo, "UPDATE copilot_jobs SET status='running'")
    with postgres.standalone_connection(repo._store) as connection:
        # A live worker holds every running job's lock.
        connection.execute(sql.SQL("SET search_path TO {}").format(
            sql.Identifier(repo._store.get().database_schema)))
        for row in connection.execute("SELECT id FROM copilot_jobs").fetchall():
            connection.execute(
                "SELECT pg_advisory_lock(hashtextextended(current_schema() || %s, 0))",
                (":job:" + row["id"],),
            )
        waiting = repo.enqueue_copilot_job(team["id"], "waiting", "scan", {})

        with repo.claim_copilot_job() as job:
            assert job is not None and job["id"] == waiting["id"]


def test_finished_jobs_past_retention_are_purged_and_open_ones_kept(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    for key in ("old", "recent", "open"):
        repo.enqueue_copilot_job(team["id"], key, "scan", {})
    _sql(repo, """UPDATE copilot_jobs SET status='complete',
        finished_at=NOW() - INTERVAL '40 days' WHERE dedupe_key='old'""")
    _sql(repo, """UPDATE copilot_jobs SET status='failed',
        finished_at=NOW() - INTERVAL '1 day' WHERE dedupe_key='recent'""")

    assert repo.purge_finished_jobs(30) == 1

    with postgres.connect(repo._store) as connection:
        left = {row["dedupe_key"] for row in connection.execute(
            "SELECT dedupe_key FROM copilot_jobs").fetchall()}
    assert left == {"recent", "open"}
