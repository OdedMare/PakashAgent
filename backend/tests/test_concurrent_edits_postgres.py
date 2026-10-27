"""Two managers editing at once, against a real PostgreSQL.

Skipped without `CHAT_TEST_DSN`, like `test_admin_postgres.py`. Each run gets
a throwaway schema, so it never touches real data.

The checks these exercise live in SQL on purpose -- a revision compared in
the `UPDATE` itself, a slot compared under the row lock -- so a fake
repository cannot prove them.
"""

import os
import uuid
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from app.common.actor import acting_as
from app.common.config import Settings
from app.common.errors import ASSIGNMENT_MOVED, PROFILE_CHANGED, ConflictError
from app.dal import database as postgres
from app.dal.repository import Repository

pytestmark = pytest.mark.skipif(
    not os.getenv("CHAT_TEST_DSN"), reason="requires a scratch PostgreSQL database"
)


@pytest.fixture
def repo():
    dsn = os.environ["CHAT_TEST_DSN"]
    schema = "edits_test_" + uuid.uuid4().hex[:12]
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


def test_a_profile_save_from_a_stale_revision_is_refused(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    repo.create_team_profile(team["id"], {"rules": []})
    opened_at = repo.team_profile_revision(team["id"])

    repo.update_team_profile(team["id"], {"rules": ["ראשון"]},
                             expected_revision=opened_at)
    with pytest.raises(ConflictError) as refused:
        repo.update_team_profile(team["id"], {"rules": ["שני"]},
                                 expected_revision=opened_at)

    assert str(refused.value) == PROFILE_CHANGED
    assert repo.team_profile(team["id"]) == {"rules": ["ראשון"]}
    assert repo.team_profile_revision(team["id"]) == opened_at + 1


def test_a_second_first_profile_is_refused_not_a_crash(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    repo.create_team_profile(team["id"], {"rules": ["ראשון"]})
    with pytest.raises(ConflictError):
        repo.create_team_profile(team["id"], {"rules": ["שני"]})
    assert repo.team_profile(team["id"]) == {"rules": ["ראשון"]}


def test_a_move_from_a_slot_the_row_already_left_is_refused(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    schedule = repo.create_schedule(team["id"], "2026-10-04", "2026-10-05")
    monday, tuesday = repo.add_slots(schedule["id"], team["id"], [
        {"shift_name": "בוקר", "slot_date": "2026-10-04"},
        {"shift_name": "בוקר", "slot_date": "2026-10-05"},
    ])
    row = repo.add_assignment(schedule["id"], team["id"], monday["id"],
                              "דנה", "מוסמכת")

    repo.move_assignment(row["id"], team["id"], tuesday["id"], "החלפה",
                         expected_slot_id=monday["id"])
    with pytest.raises(ConflictError) as refused:
        repo.move_assignment(row["id"], team["id"], monday["id"], "החזרה",
                             expected_slot_id=monday["id"])

    assert str(refused.value) == ASSIGNMENT_MOVED
    [stored] = repo.assignments(schedule["id"], team["id"])
    assert stored["slot_id"] == tuesday["id"]


def test_the_change_log_names_who_was_acting(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    with acting_as("boss:m1"):
        row = repo.append_change(team["id"], "moved", reason="החלפה")
    system = repo.append_change(team["id"], "moved", reason="בנייה")

    assert row["actor"] == "boss:m1"
    assert system["actor"] == ""


def test_a_queued_job_carries_who_queued_it(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    with acting_as("boss:m1"):
        job = repo.enqueue_copilot_job(team["id"], "key", "scan", {})
    assert job["payload"]["actor"] == "boss:m1"
