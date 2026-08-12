"""Bounded retry for transient OpenAI-compatible failures.

Only the transient family is retried. A `BadRequestError` is not transient —
it means the server rejected the shape of the request, which is what the
degradation ladder in `openai_client` exists to answer.
"""

import time

from openai import APIConnectionError, APITimeoutError, RateLimitError

_ERRORS = (RateLimitError, APIConnectionError, APITimeoutError)
_ATTEMPTS = 2
_DELAY_SECONDS = 0.3
# Deterministic output — the agent emits structured JSON, not prose.
_TEMPERATURE = 0


def create_with_retry(client, model: str, kwargs: dict):
    last_error = None
    for attempt in range(_ATTEMPTS):
        try:
            return client.chat.completions.create(
                model=model, temperature=_TEMPERATURE, **kwargs
            )
        except _ERRORS as exc:
            last_error = exc
            if attempt + 1 < _ATTEMPTS:
                time.sleep(_DELAY_SECONDS)
    raise last_error
