"""PostgreSQL connection factory driven by live runtime settings.

Ported from AiSummryIO unchanged apart from the settings prefix: the store is
read on every connect, so a database edit saved in the UI applies without a
restart, exactly as it does for the model settings.
"""

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.common.runtime_settings.runtime_settings_store import (
    RuntimeSettingsStore,
)


def connect(store: RuntimeSettingsStore) -> psycopg.Connection:
    settings = store.get()
    connection = psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        **_credentials(settings),
    )
    schema = getattr(settings, "database_schema", "")
    if schema:
        # Every unqualified name in the repositories resolves through
        # search_path, so setting it here puts the whole schema — DDL and
        # queries alike — in the configured schema without touching the SQL.
        connection.execute(
            sql.SQL("SET search_path TO {}, public").format(
                sql.Identifier(schema)
            )
        )
    return connection


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
