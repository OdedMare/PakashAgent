"""Fair access to the process-wide model concurrency limit."""

import bisect
import threading
import time
from contextlib import contextmanager
from typing import Optional

from app.common.activity import report_activity
from app.dal.database import standalone_connection
from app.dal.llm.team_context import current_team


INTERACTIVE = 0
BACKGROUND = 1


def priority_for_flow(flow: str) -> int:
    """Schedule generation is polled; every other flow has a person waiting."""
    return BACKGROUND if flow == "scheduler" else INTERACTIVE


class ModelBusy(Exception):
    """No model slot became available before an interactive wait expired."""


class ModelSlots:
    """A priority-aware, FIFO replacement for ``threading.Semaphore``.

    A semaphore permits the scheduler to release and immediately reacquire a
    slot before a woken chat thread runs. Tickets make that impossible, while
    the priority keeps interactive work ahead of queued background days.
    """

    def __init__(self, limit: int = 1) -> None:
        self._free = max(1, int(limit or 1))
        self._limit = self._free
        self._condition = threading.Condition()
        self._queue = []
        self._issued = 0

    @contextmanager
    def reserve(
        self, priority: int = INTERACTIVE, timeout: Optional[float] = None,
    ):
        report_activity("ממתין למודל…")
        self._acquire(priority, timeout)
        try:
            report_activity("המודל מכין תשובה…")
            yield
            report_activity("בודק את התוצאה…")
        finally:
            self._release()

    def _acquire(self, priority: int, timeout: Optional[float]) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            self._issued += 1
            ticket = (priority, self._issued)
            bisect.insort(self._queue, ticket)
            acquired = False
            try:
                while self._free == 0 or self._queue[0] != ticket:
                    if deadline is None:
                        self._condition.wait()
                        continue
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ModelBusy
                    self._condition.wait(remaining)
                self._free -= 1
                acquired = True
            finally:
                self._queue.remove(ticket)
                # A timed-out head can reveal the next eligible ticket.
                self._condition.notify_all()
            if not acquired:
                raise ModelBusy

    def _release(self) -> None:
        with self._condition:
            self._free = min(self._limit, self._free + 1)
            self._condition.notify_all()


class PostgresModelSlots:
    """Cross-process model slots, with an optional per-team quota.

    PostgreSQL session advisory locks disappear when a process or connection
    dies, so a crashed API or worker cannot strand capacity. The numbered
    team locks are the fairness quota (`llm_team_concurrency`; 0 means the
    whole deployment limit); the numbered slot locks enforce that limit.

    The quota used to be one call per team, so a manager's chat waited
    behind the team's own build translation, and one call that hung blocked
    the whole team.
    """

    def __init__(self, store, poll_seconds: float = 0.05) -> None:
        self._store = store
        self._poll_seconds = poll_seconds

    @contextmanager
    def reserve(
        self, priority: int = INTERACTIVE, timeout: Optional[float] = None,
    ):
        report_activity("ממתין למודל…")
        deadline = None if timeout is None else time.monotonic() + timeout
        connection = standalone_connection(self._store)
        namespace = getattr(self._store.get(), "database_schema", "") or "public"
        team_id = current_team() or "unscoped"
        team_key = namespace + ":llm:team"
        slot_key = namespace + ":llm:slot"
        team_slot = None
        slot = None
        try:
            while team_slot is None:
                team_slot = self._first_free(
                    connection, team_key, team_id, _team_limit(self._store.get()))
                if team_slot is None:
                    self._wait(deadline, priority)
            while slot is None:
                slot = self._first_free(
                    connection, slot_key, "", _global_limit(self._store.get()))
                if slot is None:
                    self._wait(deadline, priority)
            report_activity("המודל מכין תשובה…")
            yield
            report_activity("בודק את התוצאה…")
        finally:
            if slot is not None:
                self._unlock(connection, slot_key, slot)
            if team_slot is not None:
                self._unlock(connection, team_key, team_slot)
            connection.close()

    def _first_free(self, connection, namespace, prefix, limit):
        """The lock value taken, or None when all `limit` are held.

        Slot values are the bare numbers they always were; team values are
        the team id, then `team_id:1`, `team_id:2`… so a process still
        running the one-per-team code keeps contending for the same first
        lock during a rolling restart.
        """
        for index in range(limit):
            value = (prefix + (":%d" % index if index else "")) if prefix else index
            if self._try_lock(connection, namespace, value):
                return value
        return None

    @staticmethod
    def _try_lock(connection, namespace, value) -> bool:
        return bool(connection.execute(
            "SELECT pg_try_advisory_lock(hashtext(%s), hashtext(%s::text)) AS locked",
            (namespace, str(value)),
        ).fetchone()["locked"])

    @staticmethod
    def _unlock(connection, namespace, value) -> None:
        connection.execute(
            "SELECT pg_advisory_unlock(hashtext(%s), hashtext(%s::text))",
            (namespace, str(value)),
        )

    def _wait(self, deadline, priority) -> None:
        if deadline is not None and time.monotonic() >= deadline:
            raise ModelBusy
        # Interactive callers retry the lock first after a released span.
        delay = self._poll_seconds if priority == INTERACTIVE else self._poll_seconds * 2
        if deadline is not None:
            delay = min(delay, max(0, deadline - time.monotonic()))
        time.sleep(delay)


def _global_limit(settings) -> int:
    return max(1, int(getattr(settings, "llm_max_concurrency", 1) or 1))


def _team_limit(settings) -> int:
    """`llm_team_concurrency`, capped by the global limit; 0 is the limit."""
    limit = _global_limit(settings)
    try:
        team = int(getattr(settings, "llm_team_concurrency", 0) or 0)
    except (TypeError, ValueError):
        team = 0
    return min(team, limit) if team > 0 else limit


__all__ = [
    "BACKGROUND", "INTERACTIVE", "ModelBusy", "ModelSlots", "PostgresModelSlots",
    "priority_for_flow",
]
