"""Kept translations against a real PostgreSQL (D32).

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
    schema = "compiled_test_" + uuid.uuid4().hex[:12]
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


def _row(key, status="compiled", **overrides):
    row = {"source_key": key, "kind": "rule", "context": "", "text": "עדיף שדנה לא בלילות",
           "binding": False, "status": status,
           "translation": {"availability": [], "required_assignments": [], "requests": [
               {"kind": "avoid", "employees": ["דנה"], "shifts": [], "dates": [],
                "weekdays": ["שני"], "count": None, "per": "period", "is_hard": False,
                "weight": 1.0, "reason": "עדיף"}]},
           "reason": "", "expires_on": None, "question": "", "tokens": 120,
           "anchored_on": "2026-10-20"}
    row.update(overrides)
    return row


def test_a_kept_translation_round_trips_and_is_replaced(repo):
    team = repo.create_team("משמרת א", "sod-gadol")["id"]
    repo.save_compiled_sources(team, "vocab", "1:abc", [_row("k1")])
    repo.save_compiled_sources(team, "vocab", "1:abc", [_row(
        "k1", status="unresolved", reason="לא ניתן", expires_on="2026-10-23")])

    rows = repo.compiled_sources(team, "vocab", "1:abc", ["k1", "k2"])

    assert len(rows) == 1
    assert rows[0]["status"] == "unresolved" and rows[0]["reason"] == "לא ניתן"
    assert rows[0]["expires_on"] == "2026-10-23" and rows[0]["anchored_on"] == "2026-10-20"
    assert repo.compiled_sources(team, "other-vocab", "1:abc", ["k1"]) == []
    repo.touch_compiled_sources(team, ["k1"])
    repo.prune_compiled_sources(team, days=1)
    assert len(repo.compiled_sources(team, "vocab", "1:abc", ["k1"])) == 1


def test_a_sentence_keeps_the_day_it_was_first_seen(repo):
    team = repo.create_team("משמרת א", "sod-gadol")["id"]

    first = repo.source_anchors(team, ["k1"], "2026-10-20")
    later = repo.source_anchors(team, ["k1", "k2"], "2026-10-27")

    assert first == {"k1": "2026-10-20"}
    assert later == {"k1": "2026-10-20", "k2": "2026-10-27"}


def test_kept_translations_are_scoped_to_their_team(repo):
    mine = repo.create_team("משמרת א", "sod-gadol")["id"]
    theirs = repo.create_team("משמרת ב", "sod-gadol")["id"]
    repo.save_compiled_sources(mine, "vocab", "1:abc", [_row("k1")])

    assert repo.compiled_sources(theirs, "vocab", "1:abc", ["k1"]) == []
