"""The read cache over a real repository: a write retires what it cached.

Needs both `CHAT_TEST_DSN` (a scratch PostgreSQL) and a Redis
(`PAKASH_TEST_REDIS_URL`, else a `redis-server` on a free port, as in
`test_read_cache.py`); skipped without either. The point is the wiring a
fake cannot prove: a repository write, wherever it runs, reaches the cache
through the cursor before the next read.
"""

import os
import uuid
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from app.common.config import Settings
from app.common.read_cache import ReadCache
from app.common.redis_hub import RedisHub
from app.dal import database as postgres
from app.dal import write_marks
from app.dal.llm.team_context import model_team
from app.dal.repository import Repository
from tests.test_read_cache import redis_url  # noqa: F401 -- the fixture

pytestmark = pytest.mark.skipif(
    not os.getenv("CHAT_TEST_DSN"), reason="requires a scratch PostgreSQL database"
)


@pytest.fixture
def wired(redis_url):  # noqa: F811
    dsn = os.environ["CHAT_TEST_DSN"]
    schema = "cache_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    settings = Settings(_env_file=None, database_url=dsn, database_schema=schema,
                        database_host="", database_user="", database_password="",
                        database_name="", database_port=None,
                        redis_url=redis_url, redis_key_prefix="it-" + schema)
    settings.redis_cache_ttl_seconds = 300
    store = SimpleNamespace(get=lambda: settings)
    repository = Repository(store)
    hub = RedisHub(store)
    cache = ReadCache(hub, store)
    hub.client(wait=True)
    try:
        repository.initialize()
        write_marks.on_written(cache.written)
        yield repository, cache
    finally:
        write_marks.on_written(None)
        postgres.close_pool()
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _rules(repository, cache, team_id, calls):
    def load():
        calls.append(1)
        return repository.team_profile(team_id)["rules"]
    return cache.read(team_id, "rules", (), load)


def test_a_profile_save_retires_the_cached_read(wired):
    repository, cache = wired
    team = repository.create_team("משמרת א", "sod-gadol")["id"]
    repository.create_team_profile(team, {"rules": ["ראשון"]})
    calls = []

    assert _rules(repository, cache, team, calls) == ["ראשון"]
    assert _rules(repository, cache, team, calls) == ["ראשון"]
    assert len(calls) == 1  # the second came from Redis

    with model_team(team):
        repository.update_team_profile(
            team, {"rules": ["שני"]},
            expected_revision=repository.team_profile_revision(team),
        )
    assert _rules(repository, cache, team, calls) == ["שני"]
    assert len(calls) == 2


def test_a_write_with_no_team_in_context_retires_every_team(wired):
    repository, cache = wired
    teams = [repository.create_team(name, "sod-gadol")["id"] for name in ("א", "ב")]
    for team in teams:
        repository.create_team_profile(team, {"rules": [team]})
    calls = []
    for team in teams:
        _rules(repository, cache, team, calls)
    # The operator console, a commander's duties: no team in context.
    repository.update_team_profile(
        teams[0], {"rules": ["חדש"]},
        expected_revision=repository.team_profile_revision(teams[0]),
    )
    assert _rules(repository, cache, teams[0], calls) == ["חדש"]
    assert _rules(repository, cache, teams[1], calls) == [teams[1]]
    assert len(calls) == 4
