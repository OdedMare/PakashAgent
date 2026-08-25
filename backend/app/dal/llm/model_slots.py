"""Fair access to the process-wide model concurrency limit."""

import bisect
import threading
import time
from contextlib import contextmanager
from typing import Optional


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
        self._acquire(priority, timeout)
        try:
            yield
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


__all__ = [
    "BACKGROUND", "INTERACTIVE", "ModelBusy", "ModelSlots",
    "priority_for_flow",
]
