"""The queue in front of the model: who goes next, and for how long they wait.

The bug these lock down: with `llm_max_concurrency` at 1 — the shipped value,
because Ollama serves one generation at a time — a background build and a
manager's chat message compete for the same slot. A plain semaphore let the
build win repeatedly, because a thread that releases and immediately
re-acquires beats the thread it just woke. The chat request waited out day
after day of the build, outlived the proxy in front of the backend, and
arrived in the browser as a bodyless `500` from a model that was perfectly
healthy the whole time.

So these tests are about *ordering and bounds*, not about counting: what
matters is that a person waiting at a composer is never made to wait out work
nobody is watching, and that when the wait does have to end it ends in a
Hebrew sentence rather than a dead socket.
"""

import threading
import time

import pytest

from app.common.errors import AgentError
from app.dal.llm.model_slots import (
    BACKGROUND,
    INTERACTIVE,
    ModelBusy,
    ModelSlots,
    priority_for_flow,
)
from app.dal.llm.openai_client import _queue_seconds


class _Settings:
    def __init__(self, **overrides):
        self.llm_queue_seconds = 180
        for key, value in overrides.items():
            setattr(self, key, value)


def _hold(slots, order, label, priority, started, release=None):
    """Take a slot, record the order it was granted in, wait to be let go.

    `release` is `None` for the threads whose only job is to record *when*
    they were served — they hand the slot straight back so the one behind
    them can be served in the same test rather than a timeout later.
    """
    started.set()
    with slots.reserve(priority):
        order.append(label)
        if release is not None:
            release.wait(5)


# -- ordering ---------------------------------------------------------------

def test_a_re_acquiring_loop_cannot_overtake_a_waiting_request():
    """The reported bug, reduced to its mechanism.

    A background loop that releases and immediately asks again must go to the
    *back* of the queue. With a bare semaphore it usually won the race against
    the request it had just woken, which is how one chat message ended up
    behind three days of generation.
    """
    slots = ModelSlots(limit=1)
    order = []
    finished = threading.Event()

    # The build holds the slot first, as it does in the real failure.
    held = threading.Event()

    def build():
        for _ in range(3):
            with slots.reserve(BACKGROUND):
                order.append("build")
                held.set()
                time.sleep(0.05)

    def chat():
        held.wait(2)
        with slots.reserve(INTERACTIVE):
            order.append("chat")
        finished.set()

    builder = threading.Thread(target=build)
    talker = threading.Thread(target=chat)
    builder.start()
    talker.start()
    builder.join(5)
    talker.join(5)

    assert finished.is_set(), "the chat request never got the slot"
    # One build day may already be in flight when the chat asks; it must not
    # be overtaken by the days that come after it.
    assert order.index("chat") <= 1, order


def test_interactive_work_goes_ahead_of_a_queued_build():
    """Priority, not just fairness. A build is checkpointed and polled; a
    manager at a composer is not, so the person goes first even though the
    build asked earlier."""
    slots = ModelSlots(limit=1)
    order = []
    release = threading.Event()

    blocker = threading.Event()
    holder = threading.Thread(
        target=_hold, args=(slots, [], "holder", INTERACTIVE, blocker, release)
    )
    holder.start()
    blocker.wait(2)
    time.sleep(0.05)

    waiters = []
    for label, priority in (("build", BACKGROUND), ("chat", INTERACTIVE)):
        started = threading.Event()
        thread = threading.Thread(
            target=_hold, args=(slots, order, label, priority, started)
        )
        thread.start()
        started.wait(2)
        # Queued in this order on purpose: the build asks first.
        time.sleep(0.05)
        waiters.append(thread)

    release.set()
    for thread in waiters:
        thread.join(5)

    assert order == ["chat", "build"], order


def test_equal_priorities_are_served_in_arrival_order():
    slots = ModelSlots(limit=1)
    order = []
    release = threading.Event()

    blocker = threading.Event()
    holder = threading.Thread(
        target=_hold, args=(slots, [], "holder", INTERACTIVE, blocker, release)
    )
    holder.start()
    blocker.wait(2)
    time.sleep(0.05)

    waiters = []
    for label in ("first", "second", "third"):
        started = threading.Event()
        thread = threading.Thread(
            target=_hold, args=(slots, order, label, INTERACTIVE, started)
        )
        thread.start()
        started.wait(2)
        time.sleep(0.05)
        waiters.append(thread)

    release.set()
    for thread in waiters:
        thread.join(5)

    assert order == ["first", "second", "third"], order


# -- bounds -----------------------------------------------------------------

def test_a_bounded_wait_gives_up_instead_of_hanging():
    """The half of the fix that stops a starved request outliving the browser.

    Waiting forever is what turned a busy model into a bodyless 500: nothing
    ever failed, so nothing was ever reported.
    """
    slots = ModelSlots(limit=1)
    release = threading.Event()
    blocker = threading.Event()
    holder = threading.Thread(
        target=_hold, args=(slots, [], "holder", INTERACTIVE, blocker, release)
    )
    holder.start()
    blocker.wait(2)
    time.sleep(0.05)

    began = time.monotonic()
    with pytest.raises(ModelBusy):
        with slots.reserve(INTERACTIVE, timeout=0.2):
            pass
    waited = time.monotonic() - began

    release.set()
    holder.join(5)
    assert waited < 2, waited


def test_giving_up_does_not_block_whoever_is_behind():
    """A timed-out waiter leaves the queue. If it left its ticket at the head
    the next request would sleep through its own turn — a deadlock built out
    of the fix for a hang."""
    slots = ModelSlots(limit=1)
    release = threading.Event()
    blocker = threading.Event()
    holder = threading.Thread(
        target=_hold, args=(slots, [], "holder", INTERACTIVE, blocker, release)
    )
    holder.start()
    blocker.wait(2)
    time.sleep(0.05)

    order = []
    started = threading.Event()
    behind = threading.Thread(
        target=_hold, args=(slots, order, "behind", INTERACTIVE, started)
    )

    def impatient():
        try:
            with slots.reserve(INTERACTIVE, timeout=0.2):
                order.append("impatient")
        except ModelBusy:
            order.append("gave-up")

    quitter = threading.Thread(target=impatient)
    quitter.start()
    time.sleep(0.05)
    behind.start()
    started.wait(2)

    quitter.join(5)
    release.set()
    behind.join(5)

    assert order == ["gave-up", "behind"], order


def test_the_slot_comes_back_when_the_call_raises():
    """A leaked slot deadlocks the whole process — this is the one resource
    where `finally` is not a nicety."""
    slots = ModelSlots(limit=1)
    with pytest.raises(ValueError):
        with slots.reserve(INTERACTIVE):
            raise ValueError("the model server fell over")
    # Still obtainable, and without waiting.
    with slots.reserve(INTERACTIVE, timeout=0.2):
        pass


def test_more_than_one_slot_is_honoured():
    """The bound is still a bound: raising `llm_max_concurrency` for a
    batching server (vLLM, TGI) must actually let calls overlap."""
    slots = ModelSlots(limit=2)
    release = threading.Event()
    holders = []
    for _ in range(2):
        started = threading.Event()
        thread = threading.Thread(
            target=_hold,
            args=(slots, [], "holder", INTERACTIVE, started, release),
        )
        thread.start()
        started.wait(2)
        holders.append(thread)
    time.sleep(0.1)

    with pytest.raises(ModelBusy):
        with slots.reserve(INTERACTIVE, timeout=0.2):
            pass

    release.set()
    for thread in holders:
        thread.join(5)


# -- which flows may be made to wait ----------------------------------------

def test_only_generation_is_background():
    """`scheduler` is the one flow that runs as a checkpointed job the
    browser polls. Everything else is answered into a screen somebody is
    looking at, including an unknown flow — a new caller must not silently
    inherit the one priority that can be held back."""
    assert priority_for_flow("scheduler") == BACKGROUND
    for flow in ("changes", "planner", "interview", "briefing", "learn",
                 "something-new", ""):
        assert priority_for_flow(flow) == INTERACTIVE, flow


def test_a_build_queues_without_a_ceiling():
    """Nobody is waiting on it, and giving up would throw away a day of model
    time that is about to be checkpointed."""
    assert _queue_seconds(_Settings(), "scheduler") is None


def test_interactive_flows_carry_the_configured_ceiling():
    for flow in ("changes", "planner", "interview", "briefing"):
        assert _queue_seconds(_Settings(llm_queue_seconds=90), flow) == 90


def test_zero_means_wait_as_long_as_it_takes():
    """Same meaning `llm_timeout_seconds = 0` already has. Clamping it up to
    one second would turn the mildest request into the harshest setting."""
    for value in (0, -5):
        assert _queue_seconds(_Settings(llm_queue_seconds=value),
                              "changes") is None


def test_a_settings_object_without_the_field_still_resolves():
    """A runtime-settings file saved before this setting existed, or a test
    double that predates it, must not raise on the way to the model."""
    class _Older:
        pass

    assert _queue_seconds(_Older(), "changes") == 180
