"""Several replicas of one deployment agreeing through PostgreSQL (D39)."""

import os
import threading
import uuid
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from app.common.config import Settings
from app.common.runtime_settings.runtime_settings_store import RuntimeSettingsStore
from app.common.sessions import ROLE_BOSS, SharedSecret, generate_secret, issue, read
from app.dal import database as postgres
from app.dal.repository import Repository

pytestmark = pytest.mark.skipif(
    not os.getenv("CHAT_TEST_DSN"), reason="requires a scratch PostgreSQL database"
)


def _settings(schema, path=""):
    return Settings(_env_file=None, database_url=os.environ["CHAT_TEST_DSN"],
                    database_schema=schema, database_host="", database_user="",
                    database_password="", database_name="", database_port=None,
                    runtime_settings_file=path or "unused.json")


@pytest.fixture
def schema():
    dsn = os.environ["CHAT_TEST_DSN"]
    name = "deploy_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    try:
        yield name
    finally:
        postgres.close_pool()
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


@pytest.fixture
def repo(schema):
    settings = _settings(schema)
    repository = Repository(SimpleNamespace(get=lambda: settings))
    repository.initialize()
    return repository


def test_replicas_starting_together_all_initialize(schema):
    """Without the lock the losers of the `CREATE ... IF NOT EXISTS` race
    fail with a unique violation."""
    settings = _settings(schema)
    errors = []

    def boot():
        try:
            Repository(SimpleNamespace(get=lambda: settings)).initialize()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=boot) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


def test_a_cookie_issued_by_one_replica_reads_on_another(repo):
    first = SharedSecret(lambda: repo.claim_deployment_value("session_secret", generate_secret()))
    second = SharedSecret(lambda: repo.claim_deployment_value("session_secret", generate_secret()))

    cookie = issue(first, "team-1", ROLE_BOSS, 30)

    assert read(second, cookie)["team_id"] == "team-1"
    assert first() == second()


def test_a_panel_save_on_one_replica_applies_on_another(schema, repo, tmp_path):
    """Each pod has its own disk: only the database carries the save."""
    one = RuntimeSettingsStore(_settings(schema, str(tmp_path / "one.json")))
    two = RuntimeSettingsStore(_settings(schema, str(tmp_path / "two.json")))
    one.share_through(repo)
    two.share_through(repo)

    one.update({"llm_model": "shared-model", "solver_workers": 3})
    two.pull_shared()

    assert two.get().llm_model == "shared-model"
    assert two.get().solver_workers == 3
    assert not (tmp_path / "two.json").exists()


def test_the_database_connection_is_never_shared(schema, repo, tmp_path):
    """It is what the poll runs over; a replica pointed elsewhere keeps its own."""
    one = RuntimeSettingsStore(_settings(schema, str(tmp_path / "one.json")))
    one.share_through(repo)
    one.update({"database_name": "elsewhere", "llm_model": "m"})

    stored = repo.deployment_value("runtime_settings")[1]
    assert "database_" not in stored
    assert '"llm_model": "m"' in stored


def test_a_file_saved_before_the_upgrade_seeds_the_database_once(schema, repo, tmp_path):
    path = str(tmp_path / "old.json")
    RuntimeSettingsStore(_settings(schema, path)).update({"llm_model": "from-file"})

    upgraded = RuntimeSettingsStore(_settings(schema, path))
    upgraded.share_through(repo)
    upgraded.pull_shared()
    fresh = RuntimeSettingsStore(_settings(schema, str(tmp_path / "new.json")))
    fresh.share_through(repo)
    fresh.pull_shared()

    assert fresh.get().llm_model == "from-file"
    assert repo.deployment_value("runtime_settings")[0] == 1
