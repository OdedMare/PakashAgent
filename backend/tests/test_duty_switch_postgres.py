"""The one-time migration: whoever was out of the roster comes back, switched off."""

import datetime
import os
import uuid
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from app.dal import database as postgres
from app.dal.repository import Repository

from tests.test_deployment_state_postgres import _settings

pytestmark = pytest.mark.skipif(
    not os.getenv("CHAT_TEST_DSN"), reason="requires a scratch PostgreSQL database"
)


@pytest.fixture
def schema():
    dsn = os.environ["CHAT_TEST_DSN"]
    name = "duty_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    try:
        yield name
    finally:
        postgres.close_pool()
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


def _sql(schema, statement, args=()):
    with psycopg.connect(os.environ["CHAT_TEST_DSN"], autocommit=True) as connection:
        connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        return connection.execute(statement, args).fetchall() if "SELECT" in statement \
            else connection.execute(statement, args)


def _roster(schema, team):
    """Read from the table: the repository keeps a profile cache (D45)."""
    return _sql(schema, "SELECT profile FROM team_profiles WHERE team_id = %s", (team,))[0][0]["employees"]


def test_people_out_of_the_roster_come_back_switched_off_once(schema):
    repository = Repository(SimpleNamespace(get=lambda: _settings(schema)))
    repository.initialize()
    # A database from before the switch: the migration has not run yet.
    _sql(schema, "DELETE FROM deployment_state WHERE key = 'migration:roster_switch_off'")
    team = repository.create_team("צוות", "סיסמה-ארוכה-מספיק")["id"]
    future = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    repository.create_team_profile(team, {"employees": [
        {"name": "יצא", "inactive_from": "2026-01-01", "role": "לוחם"},
        {"name": "יוצא בעתיד", "inactive_from": future},
        {"name": "פעיל"},
        {"name": "לא בפול", "inactive_from": future, "notes": "לא זמין/ה: לא בפול"},
    ]})

    Repository(SimpleNamespace(get=lambda: _settings(schema))).initialize()

    people = {row["name"]: row for row in _roster(schema, team)}
    assert list(people) == ["יצא", "יוצא בעתיד", "פעיל", "לא בפול"]
    assert people["יצא"] == {"name": "יצא", "role": "לוחם", "on_duty": False}
    assert people["יוצא בעתיד"] == {"name": "יוצא בעתיד", "inactive_from": future}
    assert people["פעיל"] == {"name": "פעיל"}
    assert people["לא בפול"] == {"name": "לא בפול", "notes": "לא זמין/ה: לא בפול", "on_duty": False}

    # Someone taken out after the upgrade stays out across a restart.
    _sql(schema, "UPDATE team_profiles SET profile = %s WHERE team_id = %s", (Jsonb({"employees": [
        {"name": "יצא אחרי", "inactive_from": "2026-01-01"}]}), team))
    Repository(SimpleNamespace(get=lambda: _settings(schema))).initialize()

    assert _roster(schema, team) == [
        {"name": "יצא אחרי", "inactive_from": "2026-01-01"}]
