"""In-process change signals, per team, for the manager's screen.

An employee's submission lands on a request thread; the manager's stream
waits on the event loop. `publish()` crosses that gap with
`call_soon_threadsafe`, so a sync route can wake an async one without either
holding a thread while it waits.

**A signal carries no data.** It says *which inbox* moved, never what is in
it: the client re-reads through the ordinary boss-guarded route, so the
stream is not a second read path that would need its own scoping rules.

**Across processes over PostgreSQL** (`dal/notify.py`). `publish()` is a
`pg_notify`, and one listener thread per process -- started by the first
stream that subscribes -- hands every signal to the local subscribers, its
own process's included. A submission handled by one process therefore wakes
a manager streaming from another. Without a bus (tests), or while the
database is unreachable, delivery is in-process, and the manager's
15-second poll remains the backstop either way.
"""

import asyncio
import logging
import threading
from contextlib import contextmanager
from typing import Dict, Iterator, Set, Tuple

REQUESTS = "requests"
SWAPS = "swaps"
# A manager-chat turn moved: a check finished, the draft grew, or it ended.
CHAT = "chat"
# The commander of the workplace's מכלול changed something in it (D43).
COMMANDER = "commander"

_Subscriber = Tuple[asyncio.AbstractEventLoop, "asyncio.Queue[str]"]


_log = logging.getLogger("pakash.events")


class TeamEvents:
    def __init__(self, bus=None) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[str, Set[_Subscriber]] = {}
        # `dal.notify.PostgresSignals`, or None for this process only.
        self._bus = bus
        self._listener = None

    def publish(self, team_id: str, kind: str) -> None:
        """Wake every stream open on this team, in every process. Safe from
        any thread."""
        if self._bus is not None:
            try:
                self._bus.publish(team_id, kind)
                return
            except Exception as exc:  # noqa: BLE001 -- deliver locally instead
                _log.warning("team events falling back to this process: %s", exc)
        self._deliver(team_id, kind)

    def _deliver(self, team_id: str, kind: str) -> None:
        """Wake the streams open on this team in this process."""
        with self._lock:
            subscribers = list(self._subscribers.get(team_id, ()))
        for loop, queue in subscribers:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, kind)
            except RuntimeError:
                # The loop closed under a stream that had not unsubscribed
                # yet. Its manager is gone; there is no one to tell.
                pass

    @contextmanager
    def subscribe(self, team_id: str) -> Iterator["asyncio.Queue[str]"]:
        """A queue of signals for one team, for as long as the block runs.

        Must be entered on the event loop that will read the queue.
        """
        subscriber = (asyncio.get_running_loop(), asyncio.Queue())  # type: _Subscriber
        with self._lock:
            self._subscribers.setdefault(team_id, set()).add(subscriber)
        self._ensure_listener()
        try:
            yield subscriber[1]
        finally:
            with self._lock:
                team = self._subscribers.get(team_id)
                if team is not None:
                    team.discard(subscriber)
                    if not team:
                        del self._subscribers[team_id]

    def subscriber_count(self, team_id: str) -> int:
        with self._lock:
            return len(self._subscribers.get(team_id, ()))

    def _ensure_listener(self) -> None:
        """Start the listener once, when the first stream opens. It runs for
        the life of the process; idle, it costs one database connection."""
        if self._bus is None:
            return
        with self._lock:
            if self._listener is not None and self._listener.is_alive():
                return
            self._listener = threading.Thread(
                target=self._bus.listen, args=(self._deliver,),
                name="team-events", daemon=True,
            )
            self._listener.start()
