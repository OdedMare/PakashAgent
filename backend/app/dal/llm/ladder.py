"""The degradation ladder for OpenAI-compatible servers.

strict schema → schema → JSON mode → plain → plain with the system prompt
merged into the user turn (some local deployments reject a system role).
The strict rung exists only when the caller's schema has a strict form
(`strict_schema.py`). Only a
`BadRequestError` advances the ladder; any other exception is a real failure
and becomes an `AgentError` immediately. Adding a rung means adding it to
`attempts` -- do not scatter fallback logic through `complete`.
"""

import logging
import time
from typing import List

from openai import APITimeoutError, BadRequestError

from app.common.errors import AgentError, ModelOutputError
from app.dal.llm.completion_retry import create_with_retry
from app.dal.llm.message_merger import merge_system_into_user
from app.dal.llm.model_slots import ModelBusy
from app.dal.llm.streaming import stream_completion
from app.dal.llm.strict_schema import to_strict

_log = logging.getLogger("pakash.llm")

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
# gpt-oss on vLLM answers 400 when the text it sampled breaks its own
# "harmony" message format. Nothing about the request was wrong, so stepping
# down the ladder only throws the structured output away and fails the same
# way; the same rung is asked again instead (`_GLITCH_RETRIES` times).
_HARMONY_MARKERS = (
    "unexpected tokens remaining in message header",
    "harmonyerror",
    "harmony",
)
_GLITCH_RETRIES = 2
_TIMED_OUT = (
    "המודל לא הספיק לענות בתוך מגבלת הזמן שהוגדרה. "
    "ייתכן ששרת המודל תקוע; אם הוא פשוט איטי, "
    "אפשר להעלות את 'זמן מרבי לתשובת המודל' בהגדרות."
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


def is_sampling_glitch(error) -> bool:
    """Whether a 400 is the server failing to parse its own output."""
    return any(marker in str(error).lower() for marker in _HARMONY_MARKERS)


def complete(
    client, model, messages, max_tokens, schema, penalty, reservation,
    total_budget_seconds=None, first_rung=0, stream=None, reasoning_effort="",
):
    """One completion down the ladder. Returns `(content, usage, rung)`.

    `stream` (a `streaming.TextStream`) reads the answer as it arrives; a
    server refusing the stream is asked the same rung again without one.

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
            rungs = attempts(
                messages, max_tokens, schema, penalty, reasoning_effort, model,
            )
            first_rung = min(max(first_rung, 0), len(rungs) - 1)
            for rung, kwargs in enumerate(rungs[first_rung:], first_rung):
                try:
                    content, usage = _rung(client, model, kwargs, deadline, stream)
                except BadRequestError as exc:
                    if is_context_overflow(exc):
                        raise ModelOutputError(_TOO_LONG) from exc
                    last_bad_request = exc
                    continue
                except APITimeoutError:
                    raise AgentError(_TIMED_OUT)
                except Exception as exc:
                    _log.warning("model call failed: %s", _with_cause(exc))
                    raise AgentError("שגיאת מודל: " + _with_cause(exc))
                return content, usage, rung
    except ModelBusy:
        raise AgentError("המודל תפוס כרגע בעבודה אחרת. נסו שוב בעוד רגע.")
    raise AgentError("שגיאת מודל: " + str(last_bad_request))


def _rung(client, model, kwargs, deadline, stream):
    """One rung, asked again when the server tripped over its own output."""
    for attempt in range(_GLITCH_RETRIES + 1):
        try:
            return _one(client, model, kwargs, deadline, stream)
        except BadRequestError as exc:
            if attempt == _GLITCH_RETRIES or not is_sampling_glitch(exc) \
                    or (deadline is not None and time.monotonic() >= deadline):
                raise
            _log.info("model output glitch; asking the same rung again")


def _one(client, model, kwargs, deadline, stream):
    """`(content, usage)` of one rung, streamed when the caller asked."""
    if stream is not None and not stream.refused:
        try:
            return stream_completion(client, model, kwargs, deadline, stream.on_text)
        except BadRequestError as exc:
            if is_context_overflow(exc):
                raise
            _log.info("streaming refused; asking the same rung without it")
            stream.refused = True
    return response_data(create_with_retry(client, model, kwargs, deadline=deadline))


def attempts(
    messages, max_tokens, schema, penalty=NEUTRAL_PENALTY, reasoning_effort="",
    model_id="",
) -> List[dict]:
    """The ladder, in order."""
    rungs = []
    strict = to_strict(schema)
    if strict is not None:
        rungs.append({
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "pakash_response", "schema": strict, "strict": True},
            },
        })
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
    _add_reasoning(extras, model_id, reasoning_effort)
    if not extras:
        return rungs
    return [dict(kwargs, **extras) for kwargs in rungs]


def _add_reasoning(extras, model_id, effort):
    """How long the model thinks before answering -- most of the wait.

    Sent only when set, because a model that does not reason rejects it, and
    in the form the model family reads. Qwen3 thinks unless its chat template
    is told `enable_thinking: false`, and has no levels: `off` and `low` turn
    thinking off, `medium` and `high` leave it on. gpt-oss and the o-series
    take `reasoning_effort` and cannot stop thinking, so `off` is `low`.
    """
    if not effort:
        return
    if "qwen" in (model_id or "").lower():
        body = dict(extras.get("extra_body") or {})
        body["chat_template_kwargs"] = {"enable_thinking": effort not in ("off", "low")}
        extras["extra_body"] = body
        return
    extras["reasoning_effort"] = "low" if effort == "off" else effort


def response_data(response):
    """`(content, usage)`, with `content` an empty string when there is none.

    An empty reply is not raised here: it was still paid for, and only the
    caller's parse retry counts and logs what a rejected reply cost. gpt-oss
    produces one routinely -- trained on native tool calling, it answers a
    prompt that describes tools with `finish_reason=tool_calls` and the
    answer in `message.tool_calls`, leaving `content` empty.
    """
    content = response.choices[0].message.content or ""
    usage = response.usage
    return content, {
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }


def _with_cause(exc: BaseException) -> str:
    """The error with what caused it. The SDK's "Connection error." hides
    the reason -- an untrusted certificate, a refused port, a name that
    does not resolve -- in `__cause__`, which is the part worth reading."""
    text = str(exc) or type(exc).__name__
    cause = exc.__cause__ or exc.__context__
    seen = 0
    while cause is not None and seen < 3:
        text += " <- %s: %s" % (type(cause).__name__, str(cause)[:300])
        cause = cause.__cause__ or cause.__context__
        seen += 1
    return text
