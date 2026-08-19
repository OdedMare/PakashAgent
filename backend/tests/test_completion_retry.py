"""The transient-failure retry: what it retries, how long it waits, and the
budget that stops it.

Time is monkeypatched throughout — the point is the *decisions* about delay,
and a test that genuinely slept would take half a minute to assert them.
"""

import time

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.dal.llm import completion_retry
from app.dal.llm.completion_retry import create_with_retry


@pytest.fixture
def slept(monkeypatch):
    """Record every sleep instead of taking it."""
    recorded = []
    monkeypatch.setattr(completion_retry.time, "sleep", recorded.append)
    return recorded


def _request():
    return httpx.Request("POST", "http://localhost:8000/v1/chat/completions")


def _rate_limited(retry_after=None):
    headers = {"retry-after": str(retry_after)} if retry_after else {}
    response = httpx.Response(429, request=_request(), headers=headers)
    return RateLimitError("slow down", response=response, body=None)


def _server_error():
    response = httpx.Response(500, request=_request())
    return InternalServerError("out of memory", response=response, body=None)


def _bad_request():
    response = httpx.Response(400, request=_request())
    return BadRequestError("unsupported", response=response, body=None)


class _Client:
    """Raises its way through a script, then returns a sentinel."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, model, temperature, **kwargs):
        self.calls += 1
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
        return "ok"


def test_a_transient_failure_is_retried():
    client = _Client([APITimeoutError(request=_request())])
    assert create_with_retry(client, "m", {}) == "ok"
    assert client.calls == 2


def test_a_bad_request_is_not_retried():
    """It is the ladder's job, not this one's — the request shape is wrong and
    sending it again unchanged cannot fix it."""
    client = _Client([_bad_request()])
    with pytest.raises(BadRequestError):
        create_with_retry(client, "m", {})
    assert client.calls == 1


def test_a_local_server_5xx_is_transient():
    """vLLM out of KV cache, or Ollama mid-model-load."""
    client = _Client([_server_error()])
    assert create_with_retry(client, "m", {}) == "ok"


def test_it_gives_up_after_the_bounded_attempts(slept):
    client = _Client([APIConnectionError(request=_request())] * 5)
    with pytest.raises(APIConnectionError):
        create_with_retry(client, "m", {})
    assert client.calls == completion_retry._ATTEMPTS


def test_the_delay_grows_between_attempts(slept):
    """Geometric, not flat: a queued local server needs time to drain, and the
    original fixed 0.3s just hit it again mid-queue."""
    client = _Client([APITimeoutError(request=_request())] * 5)
    with pytest.raises(APITimeoutError):
        create_with_retry(client, "m", {})
    assert len(slept) == completion_retry._ATTEMPTS - 1
    # Full jitter makes each sleep a range, not a value; the ceiling grows.
    assert max(slept) <= completion_retry._MAX_DELAY_SECONDS
    assert slept[-1] > slept[0] * 0.5


def test_retry_after_is_obeyed_over_the_backoff_curve(slept):
    """The server knows when it will be ready; the curve is a guess."""
    client = _Client([_rate_limited(retry_after=5)])
    create_with_retry(client, "m", {})
    assert slept == [5.0]


def test_an_absurd_retry_after_is_capped(slept):
    client = _Client([_rate_limited(retry_after=9999)])
    create_with_retry(client, "m", {})
    assert slept == [completion_retry._MAX_DELAY_SECONDS]


def test_no_attempt_starts_past_the_deadline():
    """The ladder can run four of these; without a shared ceiling one request
    could hold a worker for the better part of an hour."""
    client = _Client([APITimeoutError(request=_request())] * 5)
    with pytest.raises(APITimeoutError):
        create_with_retry(
            client, "m", {}, deadline=time.monotonic() - 1
        )
    # The deadline was already past, so not even the first attempt ran... but
    # something must be raised, and it is the error from the last real try.
    assert client.calls == 0


def test_a_sleep_that_would_outlast_the_deadline_is_not_taken(slept):
    client = _Client([APITimeoutError(request=_request())] * 5)
    with pytest.raises(APITimeoutError):
        create_with_retry(
            client, "m", {}, deadline=time.monotonic() + 0.01
        )
    assert client.calls == 1
    assert slept == []
