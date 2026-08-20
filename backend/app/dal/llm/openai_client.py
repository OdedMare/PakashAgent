"""OpenAI-compatible JSON-mode LLM client.

Model, API key, base URL, and timeout come from the runtime settings store on
EVERY call, so changes saved in the UI settings panel apply immediately
without a restart.

Which model is a per-call question: `flow` picks one of three roles (see
`model_roles.py`) and the role names a model id in the runtime settings.
All roles are served by the SAME endpoint — one vLLM server publishing
several models — so they share one `OpenAI` client and one connection pool,
and switching model is a different `model` field on the request, not a
different connection. An unset role falls back to `llm_model`. Works against OpenAI itself and OpenAI-compatible servers
(Ollama, vLLM, Groq...); the default target is a local model through Ollama.

Robustness policy:
- no API key required when a custom base_url is set (local servers)
- asks for JSON mode when the server supports it, falls back if not
- merges the system prompt into the user turn for servers/models that
  reject a system role
- passes `repetition_penalty` through `extra_body` for the local servers that
  implement it, and at its default 0 omits the key entirely, so OpenAI itself
  never sees a field it would reject
- strips markdown fences from the reply
- retries once with the parse error appended before giving up
- bounds each HTTP completion by `llm_timeout_seconds`, so a hung local
  server cannot hold a request for the SDK's 600-second default

Errors leaving this package are `AgentError` in Hebrew. Nothing in
`bl/audit.py` may call this — the audit is arithmetic precisely so it cannot
be hallucinated (D3).
"""

import json
import logging
import threading
import time
from typing import List, Optional

import httpx
from openai import BadRequestError, OpenAI

from app.common.errors import AgentError
from app.dal.llm.completion_retry import create_with_retry
from app.dal.llm.json_response_parser import extract_json
from app.dal.llm.message_merger import merge_system_into_user
from app.dal.llm.model_id_extractor import extract_model_ids
from app.dal.llm.model_roles import DEFAULT, resolve_model, role_for_flow

# One initial attempt + one retry with the parse error appended.
_MAX_JSON_ATTEMPTS = 2
_DIET_MAX_COMPLETION_TOKENS = 1200
# 0 means "send no repetition_penalty at all", keeping the request byte-for-byte
# what it was for OpenAI and any other server without the extension.
_NEUTRAL_PENALTY = 0.0
# The SDK requires a non-empty key; local servers/gateways ignore it.
_LOCAL_SERVER_KEY_PLACEHOLDER = "null"
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_MODELS_PROBE_TIMEOUT_SECONDS = 30

_log = logging.getLogger("pakash.llm")

_DEFAULT_MAX_CONCURRENCY = 4
# The model server is a shared finite resource, and a single generation can
# occupy it for a minute. Bound concurrent HTTP completions process-wide so a
# burst of requests queues here instead of thrashing the server.
#
# Built on first use rather than at import, from the settings the first call
# reads: a semaphore cannot be resized once created, so this is fixed for the
# life of the process even though every other LLM setting is live. That is
# honest about what a semaphore can do — the alternative is a UI control that
# silently does nothing.
#
# The right value depends entirely on the server. One that batches
# continuously (vLLM, TGI) does its own scheduling and is *starved* by a low
# limit, because a request held back here is a request it cannot put in a
# batch. One that serves a single request at a time (Ollama's default) is only
# thrashed by a high one.
_LLM_SLOTS = None
_LLM_SLOTS_LOCK = threading.Lock()


def _slots(settings):
    global _LLM_SLOTS
    if _LLM_SLOTS is None:
        with _LLM_SLOTS_LOCK:
            if _LLM_SLOTS is None:
                limit = getattr(
                    settings, "llm_max_concurrency", _DEFAULT_MAX_CONCURRENCY
                )
                _LLM_SLOTS = threading.BoundedSemaphore(max(1, int(limit or 1)))
    return _LLM_SLOTS

# Ceiling on one logical `complete_json` call. `llm_timeout_seconds` bounds a
# single HTTP round-trip, but the ladder can run four of them and each retries
# up to three times — multiplied out, one request could hold a worker for the
# better part of an hour. This is the number that actually stops that.
_TOTAL_BUDGET_SECONDS = 300

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


def _log_call(flow, model, usage, started, attempt, failed=False, role=""):
    """One line per logical model call: what it cost and how long it took.

    This exists because nothing recorded it. `_usage` was returned from here
    and only `bl/interview.py` ever read it, and even that dropped it — so
    "how many tokens does a schedule cost" and "which flow is the slow one"
    had no answer, and every performance decision was an estimate.

    **Counts and timings only — never the prompt, the reply, or any part of
    either.** Those carry employee names, stated reasons for absence, and the
    manager's own sentences about their staff (backend/CLAUDE.md). Token
    counts describe the call without describing anybody.

    `retries` is broken out because a call that silently took two attempts
    costs double and looks identical to one that did not, in every metric
    except this one.
    """
    duration = time.monotonic() - started
    # `role` sits beside `model` rather than replacing it: the role says which
    # setting was consulted, the model says what actually ran. Reading one
    # without the other cannot tell a misrouted flow from a misconfigured
    # role — which is the whole question these lines get asked.
    _log.info(
        "llm flow=%s role=%s model=%s prompt=%d completion=%d total=%d "
        "retries=%d duration=%.1fs%s",
        flow or "unknown", role or DEFAULT, model,
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        usage.get("total_tokens", 0),
        attempt,
        duration,
        " FAILED" if failed else "",
    )


def _is_context_overflow(error) -> bool:
    """Whether a 400 means "prompt too long" rather than "bad request shape"."""
    return any(
        marker in str(error).lower() for marker in _CONTEXT_OVERFLOW_MARKERS
    )


class OpenAIJsonClient:
    """The only class callers use. `complete_json` is the method that matters."""

    def __init__(self, settings_store):
        self._store = settings_store
        self._cached_client = None
        self._cached_key = None

    def complete_json(
        self, system: str, user: str, schema=None, flow: str = "",
        role: str = "", model: str = "",
    ) -> dict:
        """Return the model's reply parsed as a JSON object.

        Adds a `_usage` key with token counts when the server reports them.
        Raises `AgentError` (Hebrew) if the reply is not valid JSON twice.

        `flow` names the caller for the telemetry line — `scheduler`,
        `interview`, `changes`, `briefing`. It is the only reason that
        parameter existed: without it every measurement reads "some model
        call", and the first question anyone asks of the numbers is which
        feature is the expensive one. It now also *routes*: `flow` picks the
        role, so a caller already naming itself for telemetry gets the right
        model without repeating the choice in a second argument that could
        drift out of step with the first.

        `role` overrides that mapping and `model` overrides both, for a
        caller that knows better than the table. Neither is needed by
        anything in `bl/` today; they exist so a one-off does not have to
        edit the mapping to get a different model.

        The model is resolved from the store HERE, per call, immediately
        before the request — so a selection saved in the settings panel
        applies to the very next call with no restart, exactly as the base
        URL and API key already did.
        """
        started = time.monotonic()
        settings = self._store.get()
        chosen_role = role or role_for_flow(flow)
        chosen_model = resolve_model(settings, chosen_role, model)
        if not settings.openai_api_key and not settings.llm_base_url:
            raise AgentError("לא הוגדר מפתח API או שרת תואם OpenAI")
        client = self._client_for(
            settings.openai_api_key, settings.llm_base_url,
            settings.llm_timeout_seconds,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        last_error = "unknown"
        max_tokens = (
            _DIET_MAX_COMPLETION_TOKENS if settings.llm_diet_mode else None
        )
        for _attempt in range(_MAX_JSON_ATTEMPTS):
            content, current = self._complete(
                client, chosen_model, messages, max_tokens, schema,
                settings.llm_repetition_penalty, _slots(settings),
            )
            # Tokens spent on a rejected reply were still spent — accumulate
            # across the retry rather than reporting only the last attempt.
            for key in usage:
                usage[key] += current.get(key, 0)
            try:
                result = extract_json(content)
                if usage["total_tokens"]:
                    result["_usage"] = usage
                _log_call(
                    flow, chosen_model, usage, started, _attempt,
                    role=chosen_role,
                )
                return result
            except json.JSONDecodeError as exc:
                last_error = str(exc)
                messages += [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": (
                        "The response was not valid JSON. "
                        "Return only one JSON object."
                    )},
                ]
        _log_call(
            flow, chosen_model, usage, started,
            _MAX_JSON_ATTEMPTS - 1, failed=True, role=chosen_role,
        )
        raise AgentError("המודל החזיר JSON לא תקין פעמיים: " + last_error)

    def list_models(
        self,
        base_url_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
    ) -> List[str]:
        """Probe `/models` over raw httpx rather than the SDK, so the admin UI
        can test a candidate endpoint before saving it."""
        settings = self._store.get()
        base = base_url_override or settings.llm_base_url
        key = api_key_override or settings.openai_api_key
        if not key and not base:
            raise AgentError("לא הוגדר חיבור למודל")
        try:
            response = httpx.get(
                (base or _DEFAULT_BASE_URL).rstrip("/") + "/models",
                headers={
                    "Authorization": "Bearer " + (
                        key or _LOCAL_SERVER_KEY_PLACEHOLDER
                    ),
                },
                timeout=_MODELS_PROBE_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return extract_model_ids(response.json())
        except Exception as exc:
            raise AgentError("לא ניתן לטעון מודלים: " + str(exc))

    def _client_for(self, api_key, base_url, timeout):
        """Reuse one OpenAI client (and its underlying httpx connection pool)
        across calls — a fresh client per call paid a TCP/TLS handshake on
        every round-trip. Re-keyed automatically when settings change
        mid-session, since the store is read per call.

        `timeout` is part of the cache key, not just a constructor argument:
        without it a client built before the setting changed would keep
        serving every later call, and the saved value would appear to do
        nothing. It bounds ONE HTTP completion — the ladder and the parse
        retry each get their own budget on top."""
        cache_key = (api_key, base_url, timeout)
        if self._cached_client is None or self._cached_key != cache_key:
            self._cached_client = OpenAI(
                api_key=api_key or _LOCAL_SERVER_KEY_PLACEHOLDER,
                base_url=base_url or None,
                timeout=timeout,
            )
            self._cached_key = cache_key
        return self._cached_client

    @staticmethod
    def _complete(client, model, messages, max_tokens, schema, penalty, slots):
        # Degradation ladder for OpenAI-compatible servers:
        # schema → JSON mode → plain → plain with the system prompt merged
        # into the user turn (some local deployments reject a system role).
        #
        # Only a BadRequestError advances the ladder; any other exception is
        # a real failure and becomes an AgentError immediately.
        last_bad_request = None
        deadline = time.monotonic() + _TOTAL_BUDGET_SECONDS
        with slots:
            for kwargs in OpenAIJsonClient._attempts(
                messages, max_tokens, schema, penalty,
            ):
                try:
                    response = create_with_retry(
                        client, model, kwargs, deadline=deadline
                    )
                except BadRequestError as exc:
                    # Not every 400 is a shape rejection. A prompt longer than
                    # the server's context window is also a 400, and stepping
                    # down the ladder cannot shorten it — every remaining rung
                    # sends the same oversized messages, fails identically, and
                    # buries the real cause behind whichever rung happened to
                    # be last. Say what actually happened instead.
                    if _is_context_overflow(exc):
                        raise AgentError(
                            "הבקשה ארוכה מדי לחלון ההקשר של המודל. "
                            "צמצם את התקופה או את כמות הנתונים."
                        )
                    last_bad_request = exc
                    continue
                except Exception as exc:
                    raise AgentError("שגיאת מודל: " + str(exc))
                return OpenAIJsonClient._response_data(response)
        raise AgentError("שגיאת מודל: " + str(last_bad_request))

    @staticmethod
    def _attempts(
        messages, max_tokens, schema, penalty=_NEUTRAL_PENALTY,
    ) -> List[dict]:
        """The ladder, in order. Adding a rung means adding it here — do not
        scatter fallback logic through `_complete`."""
        attempts = []
        if schema is not None:
            attempts.append({
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "pakash_response",
                        "schema": schema,
                    },
                },
            })
        attempts.extend([
            {"messages": messages, "response_format": {"type": "json_object"}},
            {"messages": messages},
            {"messages": merge_system_into_user(messages)},
        ])
        extras = {}
        if max_tokens is not None:
            extras["max_tokens"] = max_tokens
        # `repetition_penalty` is not an OpenAI field, so the SDK has no
        # named argument for it and it travels in `extra_body`. Sent only
        # when it is off neutral: OpenAI itself 400s on the unknown key, and
        # a 400 here is indistinguishable from the ones the ladder exists to
        # step around — every rung would fail and the real cause be lost.
        if abs(penalty - _NEUTRAL_PENALTY) > 1e-9:
            extras["extra_body"] = {"repetition_penalty": penalty}
        if not extras:
            return attempts
        return [dict(kwargs, **extras) for kwargs in attempts]

    @staticmethod
    def _response_data(response):
        content = response.choices[0].message.content
        if not content:
            raise AgentError("המודל החזיר תשובה ריקה")
        usage = response.usage
        return content, {
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        }
