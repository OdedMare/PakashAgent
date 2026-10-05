"""How long a model call may wait, read, and run in total, per flow.

Every number here is read from the settings on each call, so a value saved in
the panel applies to the next call. See `llm/CLAUDE.md` for why the
scheduler has no read timeout and no budget at all.
"""

import threading

import httpx

from app.dal.llm.model_slots import INTERACTIVE, ModelSlots, priority_for_flow

# How long to wait for the TCP/TLS handshake to a model server, in every
# configuration including "no timeout". Reaching a server that is up is a
# matter of milliseconds on a LAN and a second or two across the internet; a
# handshake still unfinished after this is a wrong host, a wrong port or a
# server that is not listening, and none of those get better by waiting.
_CONNECT_TIMEOUT_SECONDS = 30


_DEFAULT_MAX_CONCURRENCY = 1
# The model server is a shared finite resource, and a single generation can
# occupy it for a minute. Bound concurrent HTTP completions process-wide so a
# burst of requests queues here instead of thrashing the server.
#
# Built on first use rather than at import, from the settings the first call
# reads. The concurrency limit stays fixed for the life of the process.
#
# The right value depends entirely on the server. One that batches
# continuously (vLLM, TGI) does its own scheduling and is *starved* by a low
# limit, because a request held back here is a request it cannot put in a
# batch. One that serves a single request at a time (Ollama's default) is only
# thrashed by a high one.
_LLM_SLOTS = None
_LLM_SLOTS_LOCK = threading.Lock()


def slots_for(settings):
    global _LLM_SLOTS
    if _LLM_SLOTS is None:
        with _LLM_SLOTS_LOCK:
            if _LLM_SLOTS is None:
                limit = getattr(
                    settings, "llm_max_concurrency", _DEFAULT_MAX_CONCURRENCY
                )
                _LLM_SLOTS = ModelSlots(limit)
    return _LLM_SLOTS


_DEFAULT_QUEUE_SECONDS = 180


def queue_seconds(settings, flow: str):
    """How long interactive work may wait for a slot; builds wait forever."""
    if priority_for_flow(flow) != INTERACTIVE:
        return None
    try:
        seconds = int(getattr(
            settings, "llm_queue_seconds", _DEFAULT_QUEUE_SECONDS
        ))
    except (TypeError, ValueError):
        seconds = _DEFAULT_QUEUE_SECONDS
    return seconds if seconds > 0 else None

# Ceiling on one logical `complete_json` call. `llm_timeout_seconds` bounds a
# single HTTP round-trip, but the ladder can run four of them and each retries
# up to three times — multiplied out, one request could hold a worker for the
# better part of an hour. This is the number that actually stops that.
#
# **It is derived from the timeout, not fixed.** Both numbers used to be
# constants, and a deployment whose model needed more than the default said
# so by raising `llm_timeout_seconds` — which did nothing, because the budget
# below it stayed where it was and cut every call off first. Worse, once the
# timeout was raised past the budget the two inverted: the deadline expired
# before a single HTTP call could finish, so the retries and the ladder could
# never run at all and the setting appeared to make things worse.
#
# So the invariant is stated in code rather than left to whoever edits the
# settings: the budget is always a multiple of one round-trip, which is what
# makes room for the retry above it. Below this ratio the resilience
# machinery is decorative.
_BUDGET_MULTIPLIER = 2.5
_MIN_TOTAL_BUDGET_SECONDS = 300
# Daily scheduling calls are deliberately small. Letting one hold the whole
# range defeats checkpointing and makes the UI look frozen; a failed day can
# be retried without discarding its neighbours. So the scheduler gets a
# *tighter* multiple — but still a multiple, never a flat constant that a
# slow model would breach on its first attempt.
_SCHEDULER_BUDGET_MULTIPLIER = 1.5


def read_timeout_for(settings, flow: str) -> int:
    """The per-call read ceiling, which the scheduler does not have.

    **Building a schedule is the one flow with no read timeout at all**, and
    that is deliberate rather than an oversight.

    `llm_timeout_seconds` is one number for every call this product makes,
    and the calls are not comparable. A briefing is a short prompt to the
    fast model and answers in seconds; one day of scheduling is a large
    prompt to the heavy model and can take minutes on the hardware these
    deployments run on. A value chosen so the settings panel feels
    responsive is therefore, for the scheduler, a ceiling *below* the real
    answer time — and such a ceiling is not a safety net, it is a guarantee
    of failure. The observed shape of that failure is exactly this: the
    briefing works, and every build dies on `ReadTimeout` while the model
    server is still generating the answer nobody is listening for any more.

    The reason a read ceiling existed at all was to stop one request holding
    a browser connection open. Generation no longer holds one: it is a
    background job that checkpoints every day, the browser polls short reads,
    and the manager has a stop button. So the protection is obsolete for this
    flow and only its cost remains.

    Connecting stays bounded for every flow — see `httpx_timeout`. An
    unreachable server is not a slow one.
    """
    if flow == "scheduler":
        return 0
    return getattr(settings, "llm_timeout_seconds", 0) or 0


def budget_seconds(settings, flow: str):
    """The ceiling on one logical call, in seconds — or `None` for no ceiling.

    Always strictly greater than the flow's read timeout, so one HTTP attempt
    can always complete inside it. `getattr` with a default because a
    settings object predating the field — a saved file from an older version
    or a test double — must resolve rather than raise.

    A read timeout of 0 means the server is given as long as it needs, and
    the budget above it goes away with it: a deadline over an unbounded call
    could only ever fire mid-generation, throwing away an answer the server
    was still producing, which is the failure the whole setting exists to
    avoid. That is why the scheduler, whose read is never bounded, has no
    budget either — a deadline there would reintroduce the timeout under a
    different name.
    """
    timeout = read_timeout_for(settings, flow)
    if timeout <= 0:
        return None
    if flow == "scheduler":
        return max(timeout * _SCHEDULER_BUDGET_MULTIPLIER, timeout + 60)
    return max(timeout * _BUDGET_MULTIPLIER, _MIN_TOTAL_BUDGET_SECONDS)


def httpx_timeout(timeout) -> httpx.Timeout:
    """One HTTP completion's budget, phase by phase.

    `timeout` bounds the whole round-trip when it is positive. When it is 0
    or less the read is unbounded — see `_client_for` — but connecting,
    writing and waiting for a pooled connection stay bounded, because none of
    those three is the model thinking.
    """
    if not timeout or timeout <= 0:
        return httpx.Timeout(
            None,
            connect=_CONNECT_TIMEOUT_SECONDS,
            write=_CONNECT_TIMEOUT_SECONDS,
            pool=_CONNECT_TIMEOUT_SECONDS,
        )
    return httpx.Timeout(
        timeout, connect=min(_CONNECT_TIMEOUT_SECONDS, timeout)
    )
