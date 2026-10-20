"""The shared LLM limiter uses crash-safe PostgreSQL advisory locks."""

from types import SimpleNamespace

from app.dal.llm.model_slots import PostgresModelSlots
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
    def get(self):
        return SimpleNamespace(
            database_url="postgresql://db", database_schema="tenant_schema",
            llm_max_concurrency=3,
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
