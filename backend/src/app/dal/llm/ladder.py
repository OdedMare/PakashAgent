"""The degradation ladder for OpenAI-compatible servers.

schema → JSON mode → plain → plain with the system prompt merged into the
user turn (some local deployments reject a system role). Only a
`BadRequestError` advances the ladder; any other exception is a real failure
and becomes an `AgentError` immediately. Adding a rung means adding it to
`attempts` -- do not scatter fallback logic through `complete`.
"""

import time
from typing import List

from openai import APITimeoutError, BadRequestError

from app.common.errors.errors import AgentError, ModelOutputError
from app.dal.llm.completion_retry import create_with_retry
from app.dal.llm.message_merger import merge_system_into_user
from app.dal.llm.model_slots import ModelBusy

# 0 means "send no repetition_penalty at all", keeping the request byte-for-byte
# what it was for OpenAI and any other server without the extension.
NEUTRAL_PENALTY = 0.0

# Substrings local servers use when the prompt exceeds the context window.
# Matched on text because none of them use a distinct status or error code:
# vLLM, Ollama and llama.cpp all answer 400 with prose.
_CONTEXT_OVERFLOW_MARKERS = (
    "context length",
    "context window",
    "maximum context",
    "too long",
    "reduce the length",
    "exceeds",
    "n_ctx",
)
_TIMED_OUT = (
    "המודל לא הספיק לענות בתוך מגבלת הזמן שהוגדרה. "
    "אפשר להעלות את 'זמן המתנה למודל' בהגדרות, "
    "או לאפס אותו כדי להמתין כמה שנדרש."
)
_TOO_LONG = (
    "הבקשה ארוכה מדי לחלון ההקשר של המודל. "
    "צמצם את התקופה או את כמות הנתונים."
)


def is_context_overflow(error) -> bool:
    """Whether a 400 means "prompt too long" rather than "bad request shape".

    No rung can shorten a prompt, so an overflow must not advance the ladder:
    every remaining rung would fail identically and bury the real cause.
    """
    return any(marker in str(error).lower() for marker in _CONTEXT_OVERFLOW_MARKERS)


def complete(
    client, model, messages, max_tokens, schema, penalty, reservation,
    total_budget_seconds=None, first_rung=0,
):
    """One completion down the ladder. Returns `(content, usage, rung)`.

    `first_rung` skips rungs the same endpoint already refused for the same
    model and schema; each refusal is a full round-trip, paid on every call
    otherwise. `rung` is the index that answered, for the caller to remember.

    `total_budget_seconds` of `None` is "no ceiling", which is what
    `create_with_retry` already means by a `None` deadline.
    """
    deadline = (
        None if total_budget_seconds is None
        else time.monotonic() + total_budget_seconds
    )
    last_bad_request = None
    try:
        with reservation:
            rungs = attempts(messages, max_tokens, schema, penalty)
            first_rung = min(max(first_rung, 0), len(rungs) - 1)
            for rung, kwargs in enumerate(rungs[first_rung:], first_rung):
                try:
                    response = create_with_retry(client, model, kwargs, deadline=deadline)
                except BadRequestError as exc:
                    if is_context_overflow(exc):
                        raise ModelOutputError(_TOO_LONG) from exc
                    last_bad_request = exc
                    continue
                except APITimeoutError:
                    raise AgentError(_TIMED_OUT)
                except Exception as exc:
                    raise AgentError("שגיאת מודל: " + str(exc))
                content, usage = response_data(response)
                return content, usage, rung
    except ModelBusy:
        raise AgentError("המודל תפוס כרגע בעבודה אחרת. נסו שוב בעוד רגע.")
    raise AgentError("שגיאת מודל: " + str(last_bad_request))


def attempts(messages, max_tokens, schema, penalty=NEUTRAL_PENALTY) -> List[dict]:
    """The ladder, in order."""
    rungs = []
    if schema is not None:
        rungs.append({
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "pakash_response", "schema": schema},
            },
        })
    rungs.extend([
        {"messages": messages, "response_format": {"type": "json_object"}},
        {"messages": messages},
        {"messages": merge_system_into_user(messages)},
    ])
    extras = {}
    if max_tokens is not None:
        extras["max_tokens"] = max_tokens
    # `repetition_penalty` is not an OpenAI field, so it travels in
    # `extra_body`, and only off neutral: OpenAI 400s on the unknown key, and a
    # 400 here is indistinguishable from the ones the ladder steps around.
    if abs(penalty - NEUTRAL_PENALTY) > 1e-9:
        extras["extra_body"] = {"repetition_penalty": penalty}
    if not extras:
        return rungs
    return [dict(kwargs, **extras) for kwargs in rungs]


def response_data(response):
    content = response.choices[0].message.content
    if not content:
        raise AgentError("המודל החזיר תשובה ריקה")
    usage = response.usage
    return content, {
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }
