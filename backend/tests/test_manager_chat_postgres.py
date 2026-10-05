"""Optional real-database checks; CHAT_TEST_DSN must point to a scratch DB."""

import copy
import os
import uuid
from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from app.bl.manager_chat import ManagerChatService
from app.bl.schedule_service import ScheduleService
from app.common.config.settings import Settings
from app.dal.database import postgres
from app.dal.repository import Repository
from tests.test_schedule_api import _ScriptedLlm, PROFILE, MORNING
from tests.test_manager_chat import sickness

pytestmark = pytest.mark.skipif(not os.getenv("CHAT_TEST_DSN"), reason="requires a scratch PostgreSQL database")


@pytest.fixture
def real_repo():
    dsn = os.environ["CHAT_TEST_DSN"]
    schema = "chat_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    settings = Settings(_env_file=None, database_url=dsn, database_schema=schema,
                        database_host="", database_user="", database_password="",
                        database_name="", database_port=None)
    repo = Repository(SimpleNamespace(get=lambda: settings))
    try:
        repo.initialize()
        yield repo
    finally:
        postgres.close_pool()
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def seed(repo):
    team = repo.create_team("בדיקת שיחה", "test-password-only")
    repo.create_team_profile(team["id"], copy.deepcopy(PROFILE))
    period = repo.create_schedule(team["id"], "2026-10-04", "2026-10-10")
    slots = repo.replace_slots(period["id"], team["id"], [{
        "shift_name": MORNING, "slot_date": "2026-10-05", "headcount": 1,
        "start_time": "07:00", "end_time": "15:00",
    }])
    repo.add_assignment(period["id"], team["id"], slots[0]["id"], "דנה", "שיבוץ קיים")
    chat = repo.create_chat(team["id"], "manager-a")
    llm = _ScriptedLlm([sickness()])
    service = ManagerChatService(repo, llm, ScheduleService(repo, llm))
    message_id = service.start_turn(team["id"], "manager-a", chat["id"], {
        "content": "דנה חולה היום", "request_id": "request-1", "schedule_id": period["id"],
    })
    service.reply(team["id"], "manager-a", chat["id"], message_id)
    saved = repo.get_chat(team["id"], "manager-a", chat["id"])
    assert saved["messages"][-1]["status"] == "pending"
    return team["id"], period["id"], chat["id"], message_id, service


def test_real_batch_commits_assignments_absence_receipt_and_idempotency(real_repo):
    team, period, chat, message, service = seed(real_repo)
    service.apply(team, "manager-a", chat, message, True)
    assert [row["employee"] for row in real_repo.assignments(period, team)] == ["יוסי"]
    assert real_repo.availability(team)[0]["employee"] == "דנה"
    assert real_repo.get_chat(team, "manager-a", chat)["messages"][-1]["status"] == "applied"
    count = len(real_repo.change_log(team))
    service.apply(team, "manager-a", chat, message, True)
    assert len(real_repo.change_log(team)) == count


def test_real_later_failure_rolls_back_earlier_repository_commits(real_repo, monkeypatch):
    team, period, chat, message, service = seed(real_repo)
    def fail(*args, **kwargs):
        raise RuntimeError("simulated late constraint write failure")
    monkeypatch.setattr(real_repo, "set_availability", fail)
    with pytest.raises(RuntimeError):
        service.apply(team, "manager-a", chat, message, True)
    assert [row["employee"] for row in real_repo.assignments(period, team)] == ["דנה"]
    assert not real_repo.change_log(team) and not real_repo.availability(team)
    assert real_repo.get_chat(team, "manager-a", chat)["messages"][-1]["status"] == "pending"
