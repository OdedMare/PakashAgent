"""Signals between processes over PostgreSQL LISTEN/NOTIFY.

The manager's live inbox (`common/events.py`) needs "this team's inbox
moved" to reach whichever process holds the manager's stream. The database
every process already shares carries it: `publish` is one `pg_notify`, and
`listen` holds one unpooled connection per process that receives them.

The channel is named after the schema, so two deployments sharing a server
never hear each other. A notification carries `team:kind` and nothing else
-- the stream re-reads through the guarded routes (D29).
"""

import logging
import select
import time
from typing import Callable

from psycopg import sql

from app.dal.database import connect, standalone_connection

_log = logging.getLogger("pakash.events")

# How long one wait blocks before checking whether to stop.
_WAIT_SECONDS = 1.0
# How long to wait before reconnecting after the connection is lost.
_RETRY_SECONDS = 2.0


class PostgresSignals:
    def __init__(self, store, name: str = "events"):
        self._store = store
        self._name = name

    def channel(self) -> str:
        schema = getattr(self._store.get(), "database_schema", "") or "public"
        return ("%s_%s" % (schema, self._name))[:63]

    def publish(self, team_id: str, kind: str) -> None:
        with connect(self._store) as connection:
            connection.execute("SELECT pg_notify(%s, %s)", (self.channel(), "%s:%s" % (team_id, kind)))
            connection.commit()

    def listen(self, deliver: Callable[[str, str], None], running: Callable[[], bool] = lambda: True) -> None:
        """Hand every signal to `deliver(team_id, kind)` until `running()`
        turns false; reconnects on its own when the connection drops."""
        while running():
            try:
                self._listen_once(deliver, running)
            except Exception as exc:  # noqa: BLE001 -- reconnect and go on
                _log.warning("team events listener lost the database: %s", exc)
                time.sleep(_RETRY_SECONDS)

    def _listen_once(self, deliver, running) -> None:
        channel = self.channel()
        with standalone_connection(self._store) as connection:
            connection.execute(sql.SQL("LISTEN {}").format(sql.Identifier(channel)))
            pgconn = connection.pgconn
            while running() and self.channel() == channel:
                ready, _, _ = select.select([connection.fileno()], [], [], _WAIT_SECONDS)
                if not ready:
                    continue
                pgconn.consume_input()
                notice = pgconn.notifies()
                while notice is not None:
                    team_id, _, kind = notice.extra.decode("utf-8").partition(":")
                    deliver(team_id, kind)
                    notice = pgconn.notifies()
