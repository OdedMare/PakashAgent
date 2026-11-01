"""The operator's SQL against a real PostgreSQL (D28).

Skipped without `CHAT_TEST_DSN`, like `test_manager_chat_postgres.py`. Each
run gets a throwaway schema, so it never touches real data.
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
    schema = "admin_test_" + uuid.uuid4().hex[:12]
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


def _profile(*names):
    return {"employees": [{"name": name} for name in names], "shifts": [{"name": "א"}]}


def test_the_team_list_counts_without_leaking_the_hash(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    repo.update_team_admin(team["id"], {"notes": "פלוגה"})
    repo.create_team_profile(team["id"], _profile("דנה", "יוסי"))
    repo.create_schedule(team["id"], "2026-10-04", "2026-10-10")

    [row] = repo.admin_teams()

    assert row["employees"] == 2 and row["periods"] == 1 and row["shifts"] == 1
    assert row["notes"] == "פלוגה" and "max_employees" not in row
    assert row["active"] is True and row["has_profile"] is True
    assert "password_hash" not in row and "member_token" not in row


def test_the_detail_carries_roster_periods_and_the_link(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    repo.create_team_profile(team["id"], _profile("דנה"))
    repo.create_schedule(team["id"], "2026-10-04", "2026-10-10")

    detail = repo.admin_team(team["id"])

    assert [row["name"] for row in detail["profile_employees"]] == ["דנה"]
    assert len(detail["periods_list"]) == 1
    assert detail["member_token"] == team["member_token"]
    assert "password_hash" not in detail


def test_suspending_and_deleting(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    repo.create_team_profile(team["id"], _profile("דנה"))
    repo.update_team_admin(team["id"], {"active": False, "evil": "x"})

    assert repo.team_is_active(team["id"]) is False
    repo.delete_team(team["id"])
    assert repo.team_is_active(team["id"]) is False
    assert repo.admin_teams() == []
    assert repo.admin_totals()["teams"] == 0


def test_a_departed_employee_is_listed_but_not_counted_as_current(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    profile = _profile("דנה", "יוסי")
    profile["employees"][1]["inactive_from"] = "2020-01-01"
    repo.create_team_profile(team["id"], profile)

    [row] = repo.admin_teams()
    assert row["employees"] == 1 and row["roster_total"] == 2


# --- a מכלול (D43) --------------------------------------------------------------

def test_a_complex_links_existing_teams_and_scopes_its_commander(repo):
    a = repo.create_team("משמרת א", "sod-gadol")
    b = repo.create_team("משמרת ב", "sod-gadol")
    c = repo.create_team("משמרת ג", "sod-gadol")
    repo.create_team_profile(a["id"], {
        "employees": [{"name": "דנה"}],
        "shifts": [{"name": "בוקר", "start_time": "07:00", "end_time": "15:00"}],
    })
    group = repo.create_complex("מכלול צפון", "mefaked1")
    repo.set_complex_teams(group["id"], [a["id"], b["id"]])

    assert repo.authenticate_commander(group["id"], "mefaked1")["name"] == "מכלול צפון"
    with pytest.raises(Exception):
        repo.authenticate_commander(group["id"], "wrong-one")
    teams = {t["id"]: t for t in repo.complex_teams(group["id"])}
    assert set(teams) == {a["id"], b["id"]}
    assert teams[a["id"]]["shifts"][0]["name"] == "בוקר"
    assert teams[a["id"]]["employees"] == 1
    assert repo.team_in_complex(a["id"], group["id"])
    assert not repo.team_in_complex(c["id"], group["id"])
    assert repo.team_complex(a["id"])["name"] == "מכלול צפון"
    assert any(t["complex_name"] == "מכלול צפון" for t in repo.admin_teams())

    other = repo.create_complex("מכלול דרום", "mefaked2")
    with pytest.raises(Exception):
        repo.set_complex_teams(other["id"], [a["id"]])

    repo.set_complex_teams(group["id"], [b["id"]])
    assert not repo.team_in_complex(a["id"], group["id"])

    repo.update_complex(group["id"], {"active": False})
    assert not repo.team_in_complex(b["id"], group["id"])
    assert repo.list_complexes() == [{"id": other["id"], "name": "מכלול דרום"}]

    repo.delete_complex(group["id"])
    assert repo.get_team(b["id"])["complex_id"] is None


def test_commander_notices_fold_repeats_and_clear_when_seen(repo):
    team = repo.create_team("משמרת א", "sod-gadol")
    repo.record_commander_notice(team["id"], "מכלול", "שינה שיבוץ בלוח")
    repo.record_commander_notice(team["id"], "מכלול", "שינה שיבוץ בלוח")
    repo.record_commander_notice(team["id"], "מכלול", "פרסם סידור")

    notices = repo.commander_notices(team["id"])
    assert sorted((n["action"], n["count"]) for n in notices) == [
        ("פרסם סידור", 1), ("שינה שיבוץ בלוח", 2),
    ]
    repo.mark_commander_notices_seen(team["id"])
    assert repo.commander_notices(team["id"]) == []
