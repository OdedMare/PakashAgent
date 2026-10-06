"""OpenAI-compatible JSON-mode LLM client.

Model, API key, base URL, and timeout come from the runtime settings store on
EVERY call, so changes saved in the UI settings panel apply immediately
without a restart. `flow` picks one of three roles (`model_roles.py`), and
each role names its model, endpoint and key, falling back to `llm_model`,
`llm_base_url` and `openai_api_key`. Clients are cached per (key, URL,
timeout). Works against OpenAI itself and OpenAI-compatible servers (Ollama,
vLLM, Groq...); the default target is a local model through Ollama.

Robustness policy:
- no API key required when a custom base_url is set (local servers)
- the degradation ladder (`ladder.py`): schema → JSON mode → plain → merged,
  starting from the rung that last answered for the same endpoint, model and
  schema
- strips markdown fences from the reply
- retries once with the parse error appended before giving up
- bounds each HTTP completion and the whole logical call (`budgets.py`)

Errors leaving this package are `AgentError` in Hebrew. Nothing in
`bl/audit` may call this — the audit is arithmetic precisely so it cannot be
hallucinated (D3).
"""

import json
import logging
import time
from typing import List, Optional

import httpx
from openai import OpenAI

from app.common.errors.errors import AgentError, ModelOutputError
from app.common.time_context.time_context import agent_time_context
from app.dal.llm import ladder
from app.dal.llm.budgets import (  # noqa: F401  (re-exported for tests)
    budget_seconds as _budget_seconds,
    httpx_timeout,
    queue_seconds,
    read_timeout_for,
    slots_for,
)
from app.dal.llm.json_response_parser import extract_json
from app.dal.llm.model_id_extractor import extract_model_ids
from app.dal.llm.model_roles import (
    resolve_api_key, resolve_base_url, resolve_model, role_for_flow,
)
from app.dal.llm.model_slots import priority_for_flow
from app.dal.llm.telemetry import log_call

# One initial attempt + one retry with the parse error appended.
_MAX_JSON_ATTEMPTS = 2
_DIET_MAX_COMPLETION_TOKENS = 1200
# The SDK requires a non-empty key; local servers/gateways ignore it.
_LOCAL_SERVER_KEY_PLACEHOLDER = "null"
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_MODELS_PROBE_TIMEOUT_SECONDS = 30
_NOT_JSON = "The response was not valid JSON. Return only one JSON object."

_log = logging.getLogger("pakash.llm")


class _Call:
    """One logical call's resolved connection: settings, role, model, client."""

    def __init__(self, settings, role: str, model: str, client, base_url: str = ""):
        self.settings, self.role, self.model, self.client = settings, role, model, client
        self.base_url = base_url


def _schema_key(schema) -> str:
    return "" if schema is None else json.dumps(schema, sort_keys=True)


class OpenAIJsonClient:
    """The only class callers use. `complete_json` is the method that matters."""

    def __init__(self, settings_store):
        self._store = settings_store
        self._cached_clients = {}
        # (endpoint, model, schema) -> the ladder rung that last answered.
        # A server that refuses `json_schema` refuses it on every call; without
        # this each call pays that 400 round-trip again before stepping down.
        # Per process and never moved back up: a restart, or a different
        # endpoint or model in the settings, starts again from the top.
        self._first_rungs = {}

    def complete_json(
        self, system: str, user: str, schema=None, flow: str = "",
        role: str = "", model: str = "", time_context: str = "",
    ) -> dict:
        """Return the model's reply parsed as a JSON object.

        Adds a `_usage` key with token counts when the server reports them.
        Raises `AgentError` (Hebrew) if the reply is not valid JSON twice.

        `flow` names the caller for telemetry *and* routes it to a role, so a
        caller names itself once. `role` and `model` override that for a
        one-off; the endpoint and key always follow the role. Everything is
        resolved here, per call, so a saved selection applies immediately.

        `time_context` lets a caller making several calls for one request pin
        the clock they all see (`agent_time_context()` otherwise), so their
        prompts stay identical up to where the request's own state differs.
        """
        started = time.monotonic()
        call = self._connect(flow, role or role_for_flow(flow), model)
        messages = [
            {"role": "system",
             "content": system.rstrip() + "\n\n" + (time_context or agent_time_context())},
            {"role": "user", "content": user},
        ]
        return self._until_json(call, messages, schema, flow, started)

    def _connect(self, flow: str, role: str, model: str) -> _Call:
        try:
            settings = self._store.get()
            api_key = resolve_api_key(settings, role)
            base_url = resolve_base_url(settings, role)
            if not api_key and not base_url:
                raise AgentError("לא הוגדר מפתח API או שרת תואם OpenAI")
            client = self._client_for(api_key, base_url, read_timeout_for(settings, flow))
            return _Call(settings, role, resolve_model(settings, role, model), client, base_url)
        except AgentError:
            raise
        except Exception as exc:
            # A malformed endpoint or an SDK initialization failure must not
            # escape as an anonymous HTTP 500.
            _log.exception("llm setup failed flow=%s role=%s", flow or "unknown", role)
            raise AgentError("לא ניתן להכין חיבור למודל. בדקו את הגדרות הספק.") from exc

    def _until_json(self, call: _Call, messages, schema, flow: str, started) -> dict:
        settings = call.settings
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        max_tokens = _DIET_MAX_COMPLETION_TOKENS if settings.llm_diet_mode else None
        last_error = "unknown"
        rung_key = (call.base_url, call.model, _schema_key(schema))
        for attempt in range(_MAX_JSON_ATTEMPTS):
            content, current, rung = ladder.complete(
                call.client, call.model, messages, max_tokens, schema,
                settings.llm_repetition_penalty,
                slots_for(settings).reserve(
                    priority_for_flow(flow), queue_seconds(settings, flow)
                ),
                _budget_seconds(settings, flow),
                self._first_rungs.get(rung_key, 0),
            )
            self._first_rungs[rung_key] = rung
            # Tokens spent on a rejected reply were still spent.
            for key in usage:
                usage[key] += current.get(key, 0)
            try:
                result = extract_json(content)
            except json.JSONDecodeError as exc:
                last_error = str(exc)
                messages = messages + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": _NOT_JSON},
                ]
                continue
            if usage["total_tokens"]:
                result["_usage"] = usage
            log_call(flow, call.model, usage, started, attempt, role=call.role)
            return result
        log_call(flow, call.model, usage, started, _MAX_JSON_ATTEMPTS - 1,
                 failed=True, role=call.role)
        raise ModelOutputError("המודל החזיר JSON לא תקין פעמיים: " + last_error, usage=usage)

    def list_models(
        self, base_url_override: Optional[str] = None,
        api_key_override: Optional[str] = None, role: str = "",
    ) -> List[str]:
        """Probe `/models` over raw httpx, so the admin UI can test a candidate
        endpoint before saving it. `role` picks which saved connection the
        overrides fall back to."""
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
                headers={"Authorization": "Bearer " + (key or _LOCAL_SERVER_KEY_PLACEHOLDER)},
                timeout=_MODELS_PROBE_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return extract_model_ids(response.json())
        except Exception as exc:
            raise AgentError("לא ניתן לטעון מודלים: " + str(exc))

    def _client_for(self, api_key, base_url, timeout):
        """Reuse one OpenAI client (and its connection pool) across calls.

        `timeout` is part of the cache key, so a saved timeout applies to the
        next call. A timeout of 0 or less means *no* read limit (the SDK reads
        0 as "time out immediately"), but connecting always keeps a ceiling --
        an unreachable server is not a slow one. See `budgets.httpx_timeout`.
        The key is part of the cache key too: two roles on one provider with
        different keys must never share a client.
        """
        cache_key = (api_key, base_url, timeout)
        if cache_key not in self._cached_clients:
            self._cached_clients[cache_key] = OpenAI(
                api_key=api_key or _LOCAL_SERVER_KEY_PLACEHOLDER,
                base_url=base_url or None,
                timeout=httpx_timeout(timeout),
            )
        return self._cached_clients[cache_key]
