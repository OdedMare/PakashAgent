"""Which teams a connection wrote for, told once the write is committed.

The read cache (`common/read_cache.py`, D50) keeps each team's heavy reads
until that team's data changes. Finding every write by hand -- a route here,
a job there, the commander's duties written into another team -- is how a
cache ends up showing a board that is no longer true. So the writes are
noticed where every one of them passes: the cursor.

- **Marked at execute.** Every pooled connection is built with
  `TrackingCursor`, which looks at each statement's first word. A write
  records the team of the work in progress (`current_team()`, set per
  request by the middleware in `main.py` and per job by `app/worker.py`);
  with none -- the operator console, a commander's route, start-up -- it
  records `""`, which retires every team's cache.
- **Told after the commit.** A mark is only reported when a pooled block
  ends (`pooled()`, used by `database.connect` and `single_statement`) or a
  job's borrowed connection commits (`database._borrow_job_connection`).
  Reporting before the commit would let a read that lands in between cache
  the old rows under the new version. It is told synchronously, before the
  request's response leaves -- not from the pool's return, which runs on a
  pool thread a moment later.

Writes to tables no cached read looks at (the job queue, login attempts,
the deployment's shared values, chat turns) are not marked: each would
otherwise retire every cache on every poll.
"""

import logging
import re
import threading
from contextlib import contextmanager
from typing import Callable, Iterable, Optional

import psycopg

_log = logging.getLogger("pakash.cache")

_MARKS = "_pakash_written_teams"
_READ_WORDS = {
    "select", "show", "set", "listen", "unlisten", "notify", "begin",
    "commit", "rollback", "savepoint", "release", "values", "explain",
}
_FIRST_WORD = re.compile(r"\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*([A-Za-z]+)", re.S)
_TARGET = re.compile(
    r"^\s*(?:insert\s+into|update|delete\s+from)\s+(?:only\s+)?\"?([A-Za-z0-9_]+)\"?",
    re.I,
)
_CTE_WRITE = re.compile(r"\b(insert|update|delete)\b", re.I)
_IGNORED_TABLES = {
    "copilot_jobs", "login_attempts", "deployment_state",
    "manager_chats", "manager_chat_messages",
}

_listener: Optional[Callable[[set], None]] = None
_listener_lock = threading.Lock()
_telling = threading.local()


def on_written(listener: Optional[Callable[[set], None]]) -> None:
    """Who hears which teams were written. One per process; None stops."""
    global _listener
    with _listener_lock:
        _listener = listener


def is_write(query: str) -> bool:
    """Whether a statement changes data a cached read could show."""
    match = _FIRST_WORD.match(query or "")
    if match is None:
        return False
    word = match.group(1).lower()
    if word in _READ_WORDS:
        return False
    if word == "with":
        return bool(_CTE_WRITE.search(query))
    target = _TARGET.match(query)
    return not (target and target.group(1).lower() in _IGNORED_TABLES)


def mark(connection, query) -> None:
    if not isinstance(query, str):
        try:
            query = query.as_string(connection) if hasattr(query, "as_string") \
                else bytes(query).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 -- unknown shape: assume a write
            query = "unknown"
    if not is_write(query):
        return
    marks = getattr(connection, _MARKS, None)
    if marks is None:
        marks = set()
        setattr(connection, _MARKS, marks)
    # Late: `dal.llm` imports this package's `database` on its way in.
    from app.dal.llm.team_context import current_team

    marks.add(current_team())


def take(connection) -> set:
    """What `connection` wrote since the last take, cleared."""
    marks = getattr(connection, _MARKS, None)
    if not marks:
        return set()
    setattr(connection, _MARKS, None)
    return marks


def flush(connection) -> None:
    """Tell the listener what `connection` wrote since the last flush."""
    tell(take(connection))


@contextmanager
def pooled(pool):
    """`pool.connection()`, telling what it wrote once it is committed.

    Taken inside the block -- the pool may hand the connection to another
    thread the moment it is back -- and told after it, once the pool's
    context has committed. Told before the caller's response leaves, so the
    screen that made a write never re-reads the old version.
    """
    marks = set()
    try:
        with pool.connection() as connection:
            try:
                yield connection
            finally:
                marks = take(connection)
    finally:
        tell(marks)


def tell(teams: Iterable[str]) -> None:
    listener, teams = _listener, set(teams)
    if listener is None or not teams or getattr(_telling, "active", False):
        return
    # A listener that touched the database would be told about its own
    # statements, from inside this call; it is not.
    _telling.active = True
    try:
        listener(teams)
    except Exception:  # noqa: BLE001 -- a cache must never fail a write
        _log.exception("cache invalidation failed")
    finally:
        _telling.active = False


class TrackingCursor(psycopg.Cursor):
    """A cursor that marks its connection when it runs a write."""

    def execute(self, query, params=None, **kwargs):
        mark(self.connection, query)
        return super().execute(query, params, **kwargs)

    def executemany(self, query, params_seq, **kwargs):
        mark(self.connection, query)
        return super().executemany(query, params_seq, **kwargs)
