"""In-process change signals, per team, for the manager's screen.

An employee's submission lands on a request thread; the manager's stream
waits on the event loop. `publish()` crosses that gap with
`call_soon_threadsafe`, so a sync route can wake an async one without either
holding a thread while it waits.

**A signal carries no data.** It says *which inbox* moved, never what is in
it: the client re-reads through the ordinary boss-guarded route, so the
stream is not a second read path that would need its own scoping rules.

**Across processes when Redis is configured** (`redis_hub.py`). `publish()`
then goes out on the team's Redis channel, and one listener thread per
process -- started by the first stream that subscribes -- hands every message
to the local subscribers, its own process's included. A submission handled
by one worker therefore wakes a manager streaming from another. Without
Redis, or while it is down, delivery is in-process as before, and the
manager's 15-second poll remains the backstop either way.
"""

import asyncio
import logging
import threading
import time
from contextlib import contextmanager
from typing import Dict, Iterator, Optional, Set, Tuple

REQUESTS = "requests"
SWAPS = "swaps"

_Subscriber = Tuple[asyncio.AbstractEventLoop, "asyncio.Queue[str]"]


_log = logging.getLogger("pakash.events")

# How long the listener blocks on Redis before checking the settings again.
_LISTEN_SECONDS = 1.0
# How long it waits before retrying when Redis is unavailable.
_IDLE_SECONDS = 1.0


class TeamEvents:
    def __init__(self, redis=None) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[str, Set[_Subscriber]] = {}
        self._redis = redis
        self._listener = None  # type: Optional[threading.Thread]

    def publish(self, team_id: str, kind: str) -> None:
        """Wake every stream open on this team, in every process. Safe from
        any thread."""
        client = self._redis.client() if self._redis is not None else None
        if client is not None:
            try:
                client.publish(self._redis.key("events", team_id), kind)
                return
            except Exception as exc:  # noqa: BLE001 -- deliver locally instead
                self._redis.failed(exc)
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
        """Start the Redis listener once, when the first stream opens. It
        runs for the life of the process; idle, it costs one connection."""
        if self._redis is None:
            return
        with self._lock:
            if self._listener is not None and self._listener.is_alive():
                return
            self._listener = threading.Thread(
                target=self._listen, name="team-events", daemon=True,
            )
            self._listener.start()

    def _listen(self) -> None:
        while True:
            client = self._redis.client()
            if client is None:
                time.sleep(_IDLE_SECONDS)
                continue
            try:
                self._relay(client)
            except Exception as exc:  # noqa: BLE001 -- reconnect and go on
                _log.warning("team events listener lost redis: %s", exc)
                self._redis.failed(exc)

    def _relay(self, client) -> None:
        """Hand every message on our channels to local subscribers, until
        the settings change the client or the prefix under us."""
        channel = self._redis.key("events", "")
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        try:
            pubsub.psubscribe(channel + "*")
            while (
                self._redis.client() is client
                and self._redis.key("events", "") == channel
            ):
                message = pubsub.get_message(timeout=_LISTEN_SECONDS)
                if message and message.get("type") == "pmessage":
                    team_id = message["channel"][len(channel):]
                    self._deliver(team_id, message["data"])
        finally:
            pubsub.close()
