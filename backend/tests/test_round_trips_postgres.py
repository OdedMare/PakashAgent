"""Fewer round trips, same answers, against a real PostgreSQL.

Skipped without `CHAT_TEST_DSN`. Covers the single-statement autocommit path,
the pipelined `get_schedule` and the revision-keyed profile cache.
"""

import os
import uuid
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from app.common.config import Settings
from app.common.errors import NotFoundError
from app.dal import database as postgres
from app.dal.repository import Repository

pytestmark = pytest.mark.skipif(
    not os.getenv("CHAT_TEST_DSN"), reason="requires a scratch PostgreSQL database"
)


@pytest.fixture
def repo():
    dsn = os.environ["CHAT_TEST_DSN"]
    schema = "trips_test_" + uuid.uuid4().hex[:12]
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


def _schedule(repo):
    team = repo.create_team("משמרת א", "sod-gadol")["id"]
    schedule = repo.create_schedule(team, "2026-11-01", "2026-11-07")
    slots = repo.replace_slots(schedule["id"], team, [
        {"shift_name": name, "slot_date": "2026-11-0%d" % day, "headcount": 1}
        for day in range(1, 8) for name in ("בוקר", "ערב")
    ])
    repo.replace_assignments(schedule["id"], team, [
        {"slot_id": slot["id"], "employee": "דנה", "reason": "בדיקה"} for slot in slots[:5]
    ])
    return team, schedule["id"]


def test_a_pooled_connection_is_back_in_transaction_mode_after_a_single_statement(repo):
    repo.list_teams()
    with postgres.connect(repo._store) as connection:
        assert connection.autocommit is False


def test_inside_atomic_a_single_statement_still_rolls_back(repo):
    team = repo.create_team("משמרת א", "sod-gadol")["id"]
    with pytest.raises(RuntimeError):
        with postgres.atomic(repo._store):
            repo.create_schedule(team, "2026-11-01", "2026-11-07")
            repo.create_schedule(team, "2026-11-08", "2026-11-14")
            raise RuntimeError("abort")
    assert repo.list_schedules(team) == []


def test_the_pipelined_schedule_matches_its_separate_reads(repo):
    team, schedule_id = _schedule(repo)

    schedule = repo.get_schedule(schedule_id, team)

    assert schedule["slots"] == repo.slots(schedule_id, team)
    assert schedule["assignments"] == repo.assignments(schedule_id, team)
    assert len(schedule["slots"]) == 14 and len(schedule["assignments"]) == 5
    assert schedule["id"] == schedule_id and schedule["status"] == "draft"


def test_another_teams_schedule_is_not_found(repo):
    _, schedule_id = _schedule(repo)
    other = repo.create_team("משמרת ב", "sod-katan")["id"]

    with pytest.raises(NotFoundError):
        repo.get_schedule(schedule_id, other)


def test_the_pipelined_schedule_reads_inside_atomic(repo):
    team, schedule_id = _schedule(repo)
    with postgres.atomic(repo._store):
        assert len(repo.get_schedule(schedule_id, team)["slots"]) == 14


def test_a_save_from_any_process_is_seen_on_the_next_read(repo):
    team = repo.create_team("משמרת א", "sod-gadol")["id"]
    repo.create_team_profile(team, {"employees": [{"name": "דנה"}]})
    assert repo.team_profile(team) == {"employees": [{"name": "דנה"}]}
    # Written past this repository, as another replica would.
    with postgres.connect(repo._store) as connection:
        connection.execute("""UPDATE team_profiles SET profile='{"employees": []}',
            revision=revision+1, updated_at=NOW() WHERE team_id=%s""", (team,))
        connection.commit()

    assert repo.team_profile(team) == {"employees": []}


def test_editing_a_returned_profile_does_not_change_the_next_one(repo):
    team = repo.create_team("משמרת א", "sod-gadol")["id"]
    repo.create_team_profile(team, {"employees": [{"name": "דנה"}]})
    repo.team_profile(team)["employees"].append({"name": "יוסי"})

    assert repo.team_profile(team) == {"employees": [{"name": "דנה"}]}


def test_a_rolled_back_save_never_reaches_a_later_read(repo):
    """The rolled-back save and the next real one share a revision number.
    Nothing read inside `atomic()` is kept, so the first never enters the
    cache."""
    team = repo.create_team("משמרת א", "sod-gadol")["id"]
    repo.create_team_profile(team, {"v": "first"})
    repo.team_profile(team)
    with pytest.raises(RuntimeError):
        with postgres.atomic(repo._store):
            repo.update_team_profile(team, {"v": "rolled back"})
            assert repo.team_profile(team) == {"v": "rolled back"}
            raise RuntimeError("abort")
    assert repo.team_profile(team) == {"v": "first"}

    repo.update_team_profile(team, {"v": "second"})

    assert repo.team_profile(team) == {"v": "second"}


def test_a_write_that_kept_the_revision_is_still_seen(repo):
    """Hand-run SQL or a restored backup may not bump `revision`; its
    `updated_at` still differs, and that is enough to resend the document."""
    team = repo.create_team("משמרת א", "sod-gadol")["id"]
    repo.create_team_profile(team, {"v": "first"})
    repo.team_profile(team)
    with postgres.connect(repo._store) as connection:
        connection.execute("""UPDATE team_profiles SET profile='{"v": "by hand"}',
            updated_at=NOW() WHERE team_id=%s""", (team,))
        connection.commit()

    assert repo.team_profile(team) == {"v": "by hand"}


def test_a_deleted_profile_reads_as_none(repo):
    team = repo.create_team("משמרת א", "sod-gadol")["id"]
    repo.create_team_profile(team, {"v": 1})
    repo.team_profile(team)
    with postgres.connect(repo._store) as connection:
        connection.execute("DELETE FROM team_profiles WHERE team_id=%s", (team,))
        connection.commit()

    assert repo.team_profile(team) is None
