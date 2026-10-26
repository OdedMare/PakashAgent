"""The shared LLM limiter uses crash-safe PostgreSQL advisory locks."""

from contextlib import ExitStack
from types import SimpleNamespace

import pytest

from app.dal.llm.model_slots import ModelBusy, PostgresModelSlots
from app.dal.llm.team_context import model_team


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self):
        self.held = set()
        self.closed = False

    def execute(self, query, params):
        key = tuple(params)
        if "pg_try_advisory_lock" in query:
            locked = key not in self.held
            if locked:
                self.held.add(key)
            return _Result({"locked": locked})
        self.held.discard(key)
        return _Result({})

    def close(self):
        self.closed = True


class _Store:
    def __init__(self, team_concurrency=0):
        self._team = team_concurrency

    def get(self):
        return SimpleNamespace(
            database_url="postgresql://db", database_schema="tenant_schema",
            llm_max_concurrency=3, llm_team_concurrency=self._team,
        )


def test_postgres_slots_hold_a_team_quota_and_one_global_slot(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(
        "app.dal.llm.model_slots.standalone_connection",
        lambda _store: connection,
    )

    with model_team("team-a"):
        with PostgresModelSlots(_Store()).reserve():
            assert ("tenant_schema:llm:team", "team-a") in connection.held
            assert ("tenant_schema:llm:slot", "0") in connection.held

    assert connection.held == set()
    assert connection.closed


def test_one_team_may_use_every_slot_by_default(monkeypatch):
    """A team's chat no longer waits behind its own build's translation, and
    one hung call no longer stops the whole team."""
    connection = _Connection()
    monkeypatch.setattr(
        "app.dal.llm.model_slots.standalone_connection",
        lambda _store: connection,
    )
    slots = PostgresModelSlots(_Store(), poll_seconds=0)
    with model_team("team-a"), ExitStack() as stack:
        for _ in range(3):
            stack.enter_context(slots.reserve(timeout=0.01))
        assert {("tenant_schema:llm:slot", str(n)) for n in range(3)} <= connection.held
        with pytest.raises(ModelBusy):
            stack.enter_context(slots.reserve(timeout=0.01))
    assert connection.held == set()


def test_a_team_quota_still_holds_when_set(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(
        "app.dal.llm.model_slots.standalone_connection",
        lambda _store: connection,
    )
    slots = PostgresModelSlots(_Store(team_concurrency=1), poll_seconds=0)
    with model_team("team-a"), slots.reserve():
        with pytest.raises(ModelBusy):
            with slots.reserve(timeout=0.01):
                pass
        with model_team("team-b"), slots.reserve(timeout=0.01):
            pass
