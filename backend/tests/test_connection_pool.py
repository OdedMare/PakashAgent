"""The connection pool: that it is one, and that it still respects live settings.

No database. What matters here is the *keying* — a pool that ignored a settings
change would keep serving connections to the old host forever, which is a far
more confusing failure than the per-query handshake it was built to remove.
"""

import pytest

from app.dal.database import postgres


class _Settings:
    def __init__(self, **overrides):
        self.database_url = "postgresql://u:p@localhost:5432/db"
        self.database_user = "u"
        self.database_password = "p"
        self.database_host = "localhost"
        self.database_port = 5432
        self.database_name = "db"
        self.database_schema = "pakash"
        for key, value in overrides.items():
            setattr(self, key, value)


class _FakePool:
    """Stands in for `ConnectionPool`, recording construction and closure."""

    built = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        _FakePool.built.append(self)

    def close(self):
        self.closed = True

    def connection(self):
        return "connection"


@pytest.fixture(autouse=True)
def fake_pool(monkeypatch):
    _FakePool.built = []
    monkeypatch.setattr(postgres, "ConnectionPool", _FakePool)
    # `check` is read off the real class as an attribute; the fake has none.
    monkeypatch.setattr(
        postgres.ConnectionPool, "check_connection", None, raising=False
    )
    postgres._pool, postgres._pool_key = None, None
    yield
    postgres._pool, postgres._pool_key = None, None


def _store(settings):
    return type("Store", (), {"get": staticmethod(lambda: settings)})()


def test_one_pool_is_reused_across_calls():
    """The whole point: the handshake is paid once, not once per query."""
    store = _store(_Settings())
    postgres.connect(store)
    postgres.connect(store)
    postgres.connect(store)
    assert len(_FakePool.built) == 1


def test_changing_the_database_rebuilds_the_pool():
    """A database edit saved in the UI must take effect, exactly as a model
    edit does — otherwise the setting silently does nothing."""
    settings = _Settings()
    store = _store(settings)
    postgres.connect(store)
    settings.database_host = "elsewhere"
    postgres.connect(store)
    assert len(_FakePool.built) == 2


def test_the_replaced_pool_is_closed_not_dropped():
    """Leaving it to the garbage collector leaks its open sockets."""
    settings = _Settings()
    store = _store(settings)
    postgres.connect(store)
    first = _FakePool.built[0]
    settings.database_name = "other"
    postgres.connect(store)
    assert first.closed is True


def test_the_schema_is_configured_per_connection_not_per_query():
    """`search_path` is connection state. Setting it at configure time is the
    round-trip this module exists to stop paying."""
    postgres.connect(_store(_Settings()))
    assert _FakePool.built[0].kwargs["configure"] is not None


def test_no_schema_means_no_configure_hook():
    postgres.connect(_store(_Settings(database_schema="")))
    assert _FakePool.built[0].kwargs["configure"] is None


def test_close_pool_clears_the_key_so_the_next_call_rebuilds():
    store = _store(_Settings())
    postgres.connect(store)
    postgres.close_pool()
    postgres.connect(store)
    assert len(_FakePool.built) == 2
