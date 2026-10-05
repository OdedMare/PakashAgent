"""Pooled PostgreSQL connections driven by live runtime settings.

The store is read on every `connect()`, so a database edit saved in the UI
applies without a restart, exactly as it does for the model settings.

**Connections are pooled.** They were not originally: every query opened a
fresh `psycopg.connect()`, paying a TCP handshake, authentication and a
`SET search_path` round-trip before running any SQL — and a single page load
issues several queries. The pool keeps that cost to once per connection
rather than once per query.

The pool is rebuilt when the database settings change, keyed the same way
`dal/llm/` keys its OpenAI client. Without that, a database edit saved in the
UI would appear to do nothing: the pool would keep serving connections to the
old host forever, which is a far more confusing failure than a slow query.
"""

import threading

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.common.runtime_settings.runtime_settings_store import (
    RuntimeSettingsStore,
)

# Sized for the threadpool FastAPI runs sync handlers in, not for the model:
# a request blocked on a 3-minute generation is holding a worker thread, not a
# connection, because `bl/` reads what it needs and returns before the model
# is ever called.
_MIN_POOL_SIZE = 1
_MAX_POOL_SIZE = 10
# A connection that cannot be had in this long means the pool is exhausted and
# the caller should fail rather than queue indefinitely behind whatever is
# holding them.
_POOL_TIMEOUT_SECONDS = 30

_pool = None
_pool_key = None
_pool_lock = threading.Lock()


def _pool_for(settings) -> ConnectionPool:
    """One pool per distinct database configuration.

    Re-keyed on the connection settings so a change saved in the UI takes
    effect, exactly as it does for the model client. The old pool is closed
    rather than dropped: leaving it to the garbage collector leaks its open
    sockets until it happens to be collected.
    """
    global _pool, _pool_key
    key = (
        settings.database_url, settings.database_user,
        settings.database_password, settings.database_host,
        settings.database_port, settings.database_name,
        getattr(settings, "database_schema", ""),
    )
    if _pool is not None and _pool_key == key:
        return _pool
    with _pool_lock:
        if _pool is not None and _pool_key == key:
            return _pool
        old = _pool
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            kwargs=dict(
                row_factory=dict_row, **_credentials(settings)
            ),
            min_size=_MIN_POOL_SIZE,
            max_size=_MAX_POOL_SIZE,
            timeout=_POOL_TIMEOUT_SECONDS,
            configure=_configure_for(
                getattr(settings, "database_schema", "")
            ),
            # The app must start with the database still coming up — the
            # health route is what reports that, and it can only answer if
            # the process finished starting (see `main.startup`).
            open=True,
            check=ConnectionPool.check_connection,
        )
        _pool_key = key
    if old is not None:
        old.close()
    return _pool


def _configure_for(schema: str):
    """Run once per pooled connection, not once per query.

    `search_path` is connection state, so setting it at configure time is
    both correct and the point of pooling it: every unqualified name in the
    repositories resolves through it, and paying a round-trip for it on every
    query is exactly the cost this module now exists to avoid.
    """
    if not schema:
        return None

    def configure(connection):
        connection.execute(
            sql.SQL("SET search_path TO {}, public").format(
                sql.Identifier(schema)
            )
        )
        connection.commit()

    return configure


def connect(store: RuntimeSettingsStore):
    """A pooled connection, as a context manager.

    Callers use `with connect(store) as connection:` exactly as they did when
    this opened a real connection — `getconn`/`putconn` is what changed, not
    the calling convention. Note the difference that implies: leaving the
    block returns the connection to the pool instead of closing it, so a
    caller that commits must still commit.
    """
    return _pool_for(store.get()).connection()


def close_pool() -> None:
    """Release every pooled connection. For shutdown and for tests."""
    global _pool, _pool_key
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool, _pool_key = None, None


def require_schema(store: RuntimeSettingsStore) -> None:
    """Fail loudly if the configured schema does not exist.

    The app creates its tables but deliberately not the schema holding them,
    so a schema that was never provisioned has to be reported rather than
    worked around. `search_path` will not do that reporting: an unresolvable
    name in it is silently skipped, sending every CREATE TABLE to `public`.
    """
    settings = store.get()
    schema = getattr(settings, "database_schema", "")
    if not schema:
        return
    # Deliberately NOT pooled. The pool's `configure` sets `search_path` to
    # this very schema on every connection it hands out, so borrowing one to
    # ask whether the schema exists puts the question after the assumption.
    # This is also the one query that runs before the app is known to work.
    with psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        **_credentials(settings),
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            (schema,),
        ).fetchone()
    if not exists:
        raise RuntimeError(
            "schema %r does not exist in the target database; create it "
            "before starting the app (CREATE SCHEMA %s)" % (schema, schema)
        )


def _credentials(settings) -> dict:
    """Explicit fields override whatever the URL carries; empty means
    "not set", so it must not be passed at all."""
    optional = {
        "user": settings.database_user,
        "password": settings.database_password,
        "host": settings.database_host,
        "dbname": settings.database_name,
    }
    credentials = {key: value for key, value in optional.items() if value}
    if settings.database_port is not None:
        credentials["port"] = settings.database_port
    return credentials
