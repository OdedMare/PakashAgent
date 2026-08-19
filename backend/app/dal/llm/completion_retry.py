"""Bounded retry for transient OpenAI-compatible failures.

Only the transient family is retried. A `BadRequestError` is not transient —
it means the server rejected the shape of the request, which is what the
degradation ladder in `openai_client` exists to answer.

**Why the delay grows.** The original fixed 0.3s came from a hosted API,
where a 429 means "you sent too many per minute" and a short pause genuinely
clears it. The local servers this actually runs against behave differently: a
busy vLLM or Ollama does not reject the request, it *queues* it, and the
failure surfaces as `APITimeoutError` after the full timeout has already
elapsed. Retrying 0.3s later hits a server that is still working through the
same queue. Backing off geometrically gives it time to drain.

**Why the jitter.** Several workers hitting one local model server tend to
time out together — one long generation blocks everybody. Without jitter they
would then retry in lockstep, reconverging on the same instant and rebuilding
the pileup they were backing off from.

**Why there is a total budget.** `llm_timeout_seconds` bounds one HTTP call,
and the degradation ladder can run four of them, each with its own retries.
Multiplied out, a pathological request could hold a worker for many minutes.
`deadline` is the ceiling on the whole logical call: a retry that could not
finish before it is not attempted at all.
"""

import random
import time

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

_ERRORS = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    # A local server that ran out of KV cache or was mid-restart answers 5xx.
    # Transient in exactly the way this retry is for.
    InternalServerError,
)
_ATTEMPTS = 3
_BASE_DELAY_SECONDS = 0.5
_BACKOFF_FACTOR = 4.0
_MAX_DELAY_SECONDS = 8.0
# Full jitter: sleep uniformly in [0, delay] rather than delay exactly.
_JITTER = 1.0
# Deterministic output — the agent emits structured JSON, not prose.
_TEMPERATURE = 0


def create_with_retry(client, model: str, kwargs: dict, deadline=None):
    """One completion, retried through the transient failures.

    `deadline` is a `time.monotonic()` value past which no further attempt is
    started. `None` means no ceiling, which is what the callers that have no
    budget of their own pass.
    """
    last_error = None
    for attempt in range(_ATTEMPTS):
        if _out_of_time(deadline):
            break
        try:
            return client.chat.completions.create(
                model=model, temperature=_TEMPERATURE, **kwargs
            )
        except _ERRORS as exc:
            last_error = exc
            if attempt + 1 >= _ATTEMPTS:
                break
            delay = _delay(attempt, exc)
            # Sleeping past the deadline only to fail on the next check wastes
            # the very budget the deadline exists to protect.
            if _out_of_time(deadline, delay):
                break
            time.sleep(delay)
    if last_error is None:
        # The deadline was already spent before the first attempt, so no call
        # was ever made and there is no server error to re-raise. Saying so is
        # the point: without this the bare `raise None` became a TypeError,
        # which reads as a bug in this file rather than as the budget doing
        # exactly what it exists to do.
        raise APITimeoutError(request=None)
    raise last_error


def _delay(attempt: int, error) -> float:
    """How long to wait before the next attempt.

    A server that said `Retry-After` is obeyed rather than guessed at — it
    knows when it will be ready and the backoff curve does not.
    """
    stated = _retry_after(error)
    if stated is not None:
        return min(stated, _MAX_DELAY_SECONDS)
    delay = min(
        _BASE_DELAY_SECONDS * (_BACKOFF_FACTOR ** attempt), _MAX_DELAY_SECONDS
    )
    return random.uniform(delay * (1.0 - _JITTER), delay)


def _retry_after(error):
    """`Retry-After` in seconds, when the response carried one."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        value = float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _out_of_time(deadline, extra: float = 0.0) -> bool:
    return deadline is not None and time.monotonic() + extra >= deadline


__all__ = ["create_with_retry"]
