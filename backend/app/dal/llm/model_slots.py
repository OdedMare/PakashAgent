"""Who gets the model next, when only one request may be in flight.

`llm_max_concurrency` bounds how many HTTP completions this process may have
open at once, and against Ollama — the shipped target — that bound is 1. So
every model call in the process queues, and the only interesting question is
the order of the queue.

A plain `threading.Semaphore` answers that question badly here, in two ways
that compound:

**It bargains, so a loop can starve a waiter.** `release()` wakes a waiter,
but the woken thread still has to be scheduled before it can take the slot.
A thread that releases and immediately re-acquires — which is exactly the
shape of `bl/scheduler.py` generating a period one day at a time — usually
wins that race against the thread it just woke. Measured on a six-day build,
a chat request that asked for the slot first was overtaken twice and waited
out three whole days of generation. On a real model at a minute a day, "the
manager is third in line for their own question" becomes "the manager waits
out the entire build".

**It waits forever.** `llm_timeout_seconds = 0` means "wait as long as the
server needs", and that is right for an answer being generated *for you*.
Queuing is not that: nothing is being produced while a request waits here, so
there is no answer to throw away by giving up. Left unbounded, a starved
request outlives the browser and every proxy in front of it, and what the
manager sees is a dead connection — a bare `500` with no body, from a server
that never actually failed. That was the reported bug: the chat 500s while
the model itself is perfectly healthy, just busy building.

So this hands the slot out in **arrival order**, and lets an interactive call
— a manager waiting at a composer — go in front of a background build that
nobody is watching. It is the same reasoning `llm_timeout_seconds` is
documented with, applied to the queue instead of the call: the participant
who knows whether anyone is still waiting decides.

**Background work is never bounded and interactive work always is.** A build
that waits an extra minute costs nothing, because it is checkpointed per day
and polled. A person waiting on a composer is the opposite: past some point
the honest answer is "the model is busy", in Hebrew, on their screen —
`bl/planner.py` then answers the question with `bl/intent.py` and no model at
all, which is a better outcome than a spinner that ends in a dead socket.

Interactive work can in principle hold a build off indefinitely, and that is
the intended trade rather than an oversight: chat arrives at human pace, the
build resumes in the gaps, and a build is the thing with nobody waiting on it.
"""

import bisect
import threading
import time
from typing import List, Optional, Tuple

# Lower sorts first. Two levels rather than a number per flow: the only
# distinction that matters is whether a person is sitting in front of this
# call, and a finer scale would be a ranking nobody could justify.
INTERACTIVE = 0
BACKGROUND = 1

# Generation is the one flow that runs as a checkpointed background job the
# browser polls rather than holds open, so it is the one flow that may be
# made to wait. Everything else — `changes`, `planner`, `interview`,
# `briefing`, `learn` — is answered into a screen somebody is looking at.
_BACKGROUND_FLOWS = ("scheduler",)


def priority_for_flow(flow: str) -> int:
    """Whether a flow is waited on by a person. Unknown flows are treated as
    interactive: a new caller should not silently inherit the one priority
    that can be held back indefinitely."""
    if (flow or "").strip() in _BACKGROUND_FLOWS:
        return BACKGROUND
    return INTERACTIVE


class ModelBusy(Exception):
    """The slot did not come free before the caller's patience ran out.

    Raised rather than returned so it cannot be ignored by a caller that
    forgot to check. `dal/llm/openai_client.py` translates it into the Hebrew
    `AgentError` everything else in this package leaves as.
    """


class ModelSlots:
    """A fair, priority-aware bound on concurrent model calls.

    Not a semaphore subclass: the whole point is the ordering a semaphore
    does not give, and inheriting its interface would invite `acquire()` to
    be called without a priority — which is the bug, spelled differently.
    """

    def __init__(self, limit: int = 1) -> None:
        self._limit = max(1, int(limit or 1))
        self._free = self._limit
        # One condition guards the count and the queue together. They are
        # only ever meaningful with respect to each other: "may I go" is a
        # question about both.
        self._condition = threading.Condition()
        self._queue = []  # type: List[Tuple[int, int]]
        self._issued = 0

    def reserve(self, priority: int = INTERACTIVE,
                timeout: Optional[float] = None):
        """A context manager holding one slot for its body.

        `timeout` is the ceiling on *waiting*, not on the call that follows —
        once the slot is held, the request runs for as long as it takes.
        `None` means no ceiling, which is what background work passes.
        """
        return _Reservation(self, priority, timeout)

    # -- internals ---------------------------------------------------------

    def _acquire(self, priority: int, timeout: Optional[float]) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            self._issued += 1
            # The sequence number is what makes this arrival-ordered within a
            # priority, and it is why a re-acquiring loop cannot barge: going
            # round again means taking a *later* ticket than the request
            # already waiting.
            ticket = (priority, self._issued)
            bisect.insort(self._queue, ticket)
            try:
                while self._free <= 0 or self._queue[0] != ticket:
                    if deadline is None:
                        self._condition.wait()
                        continue
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ModelBusy(
                            "no model slot came free within %ss" % timeout
                        )
                    self._condition.wait(remaining)
                self._free -= 1
            finally:
                # Leaving the queue changes who is at its head, whether this
                # call won the slot or gave up waiting for it. Both cases
                # have to wake the others or the new head sleeps through its
                # own turn.
                self._queue.remove(ticket)
                self._condition.notify_all()

    def _release(self) -> None:
        with self._condition:
            self._free = min(self._limit, self._free + 1)
            # `notify_all` rather than `notify`: only the thread at the head
            # of the queue may take this slot, and `notify` could wake any
            # other one, which would go back to sleep having spent the only
            # wakeup there was.
            self._condition.notify_all()


class _Reservation:
    """The context manager `reserve()` returns. Separate so the acquire can
    raise before anything is held, rather than inside a `with` body that
    would then have to guess whether it owns a slot."""

    def __init__(self, slots: ModelSlots, priority: int,
                 timeout: Optional[float]) -> None:
        self._slots = slots
        self._priority = priority
        self._timeout = timeout

    def __enter__(self) -> None:
        self._slots._acquire(self._priority, self._timeout)

    def __exit__(self, *exc_info) -> None:
        self._slots._release()


__all__ = [
    "BACKGROUND",
    "INTERACTIVE",
    "ModelBusy",
    "ModelSlots",
    "priority_for_flow",
]
