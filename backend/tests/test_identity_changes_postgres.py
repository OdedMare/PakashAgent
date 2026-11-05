"""Renaming and deleting from unit setup, against a real PostgreSQL.

Skipped without `CHAT_TEST_DSN`, like `test_concurrent_edits_postgres.py`.
Each run gets a throwaway schema. The point is the SQL: every stored row
that names the person or the shift follows the rename in one transaction.
"""

import os
import uuid
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from app.bl.profile_service import ProfileService
from app.common.config import Settings
from app.common.errors import AgentError
from app.dal import database as postgres
from app.dal.repository import Repository

pytestmark = pytest.mark.skipif(
    not os.getenv("CHAT_TEST_DSN"), reason="requires a scratch PostgreSQL database"
)

_PROFILE = {
    "workplace": {"name": "יחידה"},
    "employees": [
        {"name": "דנה", "eligible_shifts": ["בוקר", "ערב"]},
        {"name": "יוסי כהנ", "eligible_shifts": ["בוקר"], "trainers": ["דנה"]},
    ],
    "shifts": [
        {"name": "בוקר", "start_time": "07:00", "end_time": "15:00"},
        {"name": "ערב", "start_time": "15:00", "end_time": "23:00"},
    ],
}


@pytest.fixture
def repo():
    dsn = os.environ["CHAT_TEST_DSN"]
    schema = "identity_test_" + uuid.uuid4().hex[:12]
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


def _team(repo):
    team = repo.create_team("משמרת א", "sod-gadol")["id"]
    repo.create_team_profile(team, _PROFILE)
    schedule = repo.create_schedule(team, "2026-10-04", "2026-10-05")
    morning, evening = repo.add_slots(schedule["id"], team, [
        {"shift_name": "בוקר", "slot_date": "2026-10-04"},
        {"shift_name": "ערב", "slot_date": "2026-10-04"},
    ])
    repo.add_assignment(schedule["id"], team, morning["id"], "יוסי כהנ", "שובץ")
    repo.add_assignment(schedule["id"], team, evening["id"], "דנה", "שובץ")
    repo.set_availability(team, "יוסי כהנ", "2026-10-05", shift_name="ערב")
    repo.create_preference(team, "מעדיף בקרים", kind="employee", subject="יוסי כהנ")
    return team, schedule["id"]


def test_a_rename_reaches_every_row_and_is_logged(repo):
    team, schedule = _team(repo)
    service = ProfileService(repo)
    service.update(team, renamed_employees={"יוסי כהנ": "יוסי כהן"},
                   renamed_shifts={"ערב": "ערבית"},
                   expected_revision=repo.team_profile_revision(team))

    profile = repo.team_profile(team)
    assert [row["name"] for row in profile["employees"]] == ["דנה", "יוסי כהן"]
    assert [row["name"] for row in profile["shifts"]] == ["בוקר", "ערבית"]
    assert profile["employees"][0]["eligible_shifts"] == ["בוקר", "ערבית"]
    assert profile["employees"][1]["trainers"] == ["דנה"]
    by_name = {row["employee"]: row for row in repo.assignments(schedule, team)}
    assert set(by_name) == {"דנה", "יוסי כהן"}
    assert {row["shift_name"] for row in repo.slots(schedule, team)} == {"בוקר", "ערבית"}
    [constraint] = repo.availability(team)
    assert (constraint["employee"], constraint["shift_name"]) == ("יוסי כהן", "ערבית")
    assert [row["subject"] for row in repo.preferences(team)] == ["יוסי כהן"]
    actions = [(row["action"], row["replaced_employee"]) for row in repo.change_log(team)]
    assert ("renamed", "יוסי כהנ") in actions


def test_a_rename_to_a_taken_name_writes_nothing(repo):
    team, schedule = _team(repo)
    with pytest.raises(AgentError):
        ProfileService(repo).update(team, renamed_employees={"יוסי כהנ": "דנה"})
    assert {row["employee"] for row in repo.assignments(schedule, team)} == {"דנה", "יוסי כהנ"}


def test_deleting_a_soldier_clears_their_draft_rows(repo):
    team, schedule = _team(repo)
    ProfileService(repo).update(team, removed_employees=["יוסי כהנ"])

    profile = repo.team_profile(team)
    assert [row["name"] for row in profile["employees"]] == ["דנה"]
    assert [row["employee"] for row in repo.assignments(schedule, team)] == ["דנה"]
    assert repo.availability(team) == []
    assert repo.preferences(team) == []
    removed = [row for row in repo.change_log(team) if row["action"] == "removed"]
    assert [row["employee"] for row in removed] == ["יוסי כהנ"]


def test_a_soldier_on_a_published_week_is_not_deleted(repo):
    team, schedule = _team(repo)
    repo.set_schedule_status(schedule, team, "published")
    revision = repo.team_profile_revision(team)
    with pytest.raises(AgentError):
        ProfileService(repo).update(team, removed_employees=["יוסי כהנ"])
    # The profile save rolled back with it.
    assert repo.team_profile_revision(team) == revision
    assert len(repo.team_profile(team)["employees"]) == 2
