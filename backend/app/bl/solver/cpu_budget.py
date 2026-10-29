"""How many solver threads this process runs at once.

Each solve asks CP-SAT for `solver_workers` threads (8 by default) for up to
`solver_time_limit_seconds`. Builds for several teams at once, plus a chat
turn's preview, used to start them all together: on a four-core machine
three solves ran 24 threads, each got a fraction of the time it was given,
and the API serving the same process slowed with them. A solve now takes
its threads from a budget sized to the machine and waits for them when
another solve holds them -- so it gets the time its limit promises.

`PAKASH_SOLVER_CPU_BUDGET` overrides the size (default: the CPU count).
Set it per process when the API and a separate worker share one machine.
"""

import os
import threading
from contextlib import contextmanager

from app.common.activity import report_activity


class CpuBudget:
    def __init__(self, capacity: int):
        self._capacity = max(1, int(capacity))
        self._free = self._capacity
        self._condition = threading.Condition()

    @contextmanager
    def threads(self, wanted: int):
        """Hold `wanted` threads (at most the whole budget) for the block."""
        taken = max(1, min(int(wanted), self._capacity))
        with self._condition:
            if self._free < taken:
                report_activity("ממתין לפותר האילוצים…")
            while self._free < taken:
                self._condition.wait()
            self._free -= taken
        try:
            yield taken
        finally:
            with self._condition:
                self._free += taken
                self._condition.notify_all()


def _capacity() -> int:
    configured = os.getenv("PAKASH_SOLVER_CPU_BUDGET", "")
    if configured.strip():
        return max(1, int(configured))
    return os.cpu_count() or 1


BUDGET = CpuBudget(_capacity())
