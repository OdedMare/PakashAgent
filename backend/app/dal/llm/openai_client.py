"""OpenAI-compatible JSON-mode LLM client.

Model, API key, base URL, and timeout come from the runtime settings store on
EVERY call, so changes saved in the UI settings panel apply immediately
without a restart.

Which model, endpoint and API key to use is a per-call question: `flow` picks
one of three roles (see `model_roles.py`) and the role names all three in
runtime settings. Unset role fields fall back to `llm_model`, `llm_base_url`
and `openai_api_key`, so roles may sit on different providers with different
credentials. Clients are cached per (key, URL, timeout), so roles sharing a
connection also share its pool while roles on different ones stay separate.
Works against OpenAI itself and OpenAI-compatible servers
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
  server cannot hold a request indefinitely, and bounds the whole logical
  call by a multiple of it (`_budget_seconds`) so the ladder and the retries
  above it always have room to run

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
from openai import APITimeoutError, BadRequestError, OpenAI

from app.common.errors import AgentError
from app.common.time_context import agent_time_context
from app.dal.llm.completion_retry import create_with_retry
from app.dal.llm.json_response_parser import extract_json
from app.dal.llm.message_merger import merge_system_into_user
from app.dal.llm.model_id_extractor import extract_model_ids
from app.dal.llm.model_roles import (
    DEFAULT,
    resolve_api_key,
    resolve_base_url,
    resolve_model,
    role_for_flow,
)
from app.dal.llm.model_slots import (
    INTERACTIVE,
    ModelBusy,
    ModelSlots,
    priority_for_flow,
)

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
# How long to wait for the TCP/TLS handshake to a model server, in every
# configuration including "no timeout". Reaching a server that is up is a
# matter of milliseconds on a LAN and a second or two across the internet; a
# handshake still unfinished after this is a wrong host, a wrong port or a
# server that is not listening, and none of those get better by waiting.
_CONNECT_TIMEOUT_SECONDS = 30

_log = logging.getLogger("pakash.llm")

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


def _slots(settings):
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


def _queue_seconds(settings, flow: str):
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

    Connecting stays bounded for every flow — see `_httpx_timeout`. An
    unreachable server is not a slow one.
    """
    if flow == "scheduler":
        return 0
    return getattr(settings, "llm_timeout_seconds", 0) or 0


def _budget_seconds(settings, flow: str):
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


def _httpx_timeout(timeout) -> httpx.Timeout:
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


class OpenAIJsonClient:
    """The only class callers use. `complete_json` is the method that matters."""

    def __init__(self, settings_store):
        self._store = settings_store
        self._cached_clients = {}

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

        `role` overrides that mapping and `model` overrides the model alone;
        the endpoint and key always follow the role, since a model id means
        nothing away from the server that serves it. For a
        caller that knows better than the table. Neither is needed by
        anything in `bl/` today; they exist so a one-off does not have to
        edit the mapping to get a different model.

        The model, endpoint and key are resolved from the store HERE, per call,
        immediately before the request — so a selection saved in the settings
        panel applies to the very next call with no restart.
        """
        started = time.monotonic()
        chosen_role = role or role_for_flow(flow)
        try:
            settings = self._store.get()
            chosen_model = resolve_model(settings, chosen_role, model)
            chosen_base_url = resolve_base_url(settings, chosen_role)
            chosen_api_key = resolve_api_key(settings, chosen_role)
            if not chosen_api_key and not chosen_base_url:
                raise AgentError("לא הוגדר מפתח API או שרת תואם OpenAI")
            client = self._client_for(
                chosen_api_key, chosen_base_url,
                read_timeout_for(settings, flow),
            )
        except AgentError:
            raise
        except Exception as exc:
            # Client construction happens before `_complete`, whose broad
            # wrapper normally turns provider failures into `AgentError`.
            # A malformed endpoint or an SDK initialization failure must not
            # escape that boundary as an anonymous HTTP 500.
            _log.exception(
                "llm setup failed flow=%s role=%s", flow or "unknown",
                chosen_role,
            )
            raise AgentError(
                "לא ניתן להכין חיבור למודל. בדקו את הגדרות הספק."
            ) from exc
        messages = [
            {
                "role": "system",
                "content": system.rstrip() + "\n\n" + agent_time_context(),
            },
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
                settings.llm_repetition_penalty,
                _slots(settings).reserve(
                    priority_for_flow(flow), _queue_seconds(settings, flow)
                ),
                _budget_seconds(settings, flow),
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
        role: str = "",
    ) -> List[str]:
        """Probe `/models` over raw httpx rather than the SDK, so the admin UI
        can test a candidate endpoint before saving it.

        `role` picks which saved connection the overrides fall back to, so
        the panel can list what one role's server offers rather than always
        asking the general one — with roles on different providers, the
        general endpoint's catalogue is the wrong list for two of the three
        model fields.
        """
        settings = self._store.get()
        base = base_url_override or (
            resolve_base_url(settings, role) if role else settings.llm_base_url
        )
        key = api_key_override or (
            resolve_api_key(settings, role) if role else settings.openai_api_key
        )
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
        retry each get their own budget on top.

        A timeout of 0 or less means *no* limit, and is translated to `None`
        here: the SDK reads 0 as "time out immediately", so passing it
        through would turn "wait as long as it takes" into the one thing it
        must never mean. `httpx.Timeout(None)` is explicit rather than
        omitting the argument, because leaving it out restores the SDK's own
        600-second default instead of removing the bound.

        **Unbounded applies to reading, never to connecting.** "No limit"
        exists so a model that is slow to *answer* is waited for; a server
        that never completes a TCP handshake is not answering slowly, it is
        unreachable, and waiting forever on that is what turns a mistyped
        base URL into a schedule stuck at "building day one" with nothing to
        read anywhere. So the connect phase keeps a small ceiling in every
        configuration, and only the read phase is ever unbounded."""
        cache_key = (api_key, base_url, timeout)
        if cache_key not in self._cached_clients:
            self._cached_clients[cache_key] = OpenAI(
                api_key=api_key or _LOCAL_SERVER_KEY_PLACEHOLDER,
                base_url=base_url or None,
                timeout=_httpx_timeout(timeout),
            )
        return self._cached_clients[cache_key]

    @staticmethod
    def _complete(
        client, model, messages, max_tokens, schema, penalty, reservation,
        total_budget_seconds=_MIN_TOTAL_BUDGET_SECONDS,
    ):
        # Degradation ladder for OpenAI-compatible servers:
        # schema → JSON mode → plain → plain with the system prompt merged
        # into the user turn (some local deployments reject a system role).
        #
        # Only a BadRequestError advances the ladder; any other exception is
        # a real failure and becomes an AgentError immediately.
        last_bad_request = None
        # `None` is "no ceiling", which is what `create_with_retry` already
        # means by a `None` deadline — so an unbounded call needs no branch
        # here beyond not computing one.
        deadline = (
            None if total_budget_seconds is None
            else time.monotonic() + total_budget_seconds
        )
        try:
            with reservation:
                for kwargs in OpenAIJsonClient._attempts(
                    messages, max_tokens, schema, penalty,
                ):
                    try:
                        response = create_with_retry(
                            client, model, kwargs, deadline=deadline
                        )
                    except BadRequestError as exc:
                        # Not every 400 is a shape rejection. A prompt longer
                        # than the server's context window is also a 400.
                        if _is_context_overflow(exc):
                            raise AgentError(
                                "הבקשה ארוכה מדי לחלון ההקשר של המודל. "
                                "צמצם את התקופה או את כמות הנתונים."
                            )
                        last_bad_request = exc
                        continue
                    except APITimeoutError:
                        raise AgentError(
                            "המודל לא הספיק לענות בתוך מגבלת הזמן שהוגדרה. "
                            "אפשר להעלות את 'זמן המתנה למודל' בהגדרות, "
                            "או לאפס אותו כדי להמתין כמה שנדרש."
                        )
                    except Exception as exc:
                        raise AgentError("שגיאת מודל: " + str(exc))
                    return OpenAIJsonClient._response_data(response)
        except ModelBusy:
            raise AgentError(
                "המודל תפוס כרגע בעבודה אחרת. נסו שוב בעוד רגע."
            )
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
