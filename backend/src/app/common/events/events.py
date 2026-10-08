"""In-process "something changed" signals, per team, for the manager's screen.

An employee's submission lands on a request thread; the manager's stream
waits on the event loop. `publish()` crosses that gap with
`call_soon_threadsafe`, so a sync route can wake an async one without either
holding a thread while it waits.

**A signal carries no data.** It says *which inbox* moved, never what is in
it: the client re-reads through the ordinary boss-guarded route, so the
stream is not a second read path that would need its own scoping rules.

**Per process, like `LoginThrottle`.** A submission handled by another worker
does not reach this one's subscribers; the manager's 15-second poll is the
backstop that still catches it. One worker is the deployment today.
"""

import asyncio
import threading
from contextlib import contextmanager
from typing import Dict, Iterator, Set, Tuple

REQUESTS = "requests"
SWAPS = "swaps"

_Subscriber = Tuple[asyncio.AbstractEventLoop, "asyncio.Queue[str]"]


class TeamEvents:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[str, Set[_Subscriber]] = {}

    def publish(self, team_id: str, kind: str) -> None:
        """Wake every stream open on this team. Safe from any thread."""
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
