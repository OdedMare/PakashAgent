# LLM client (`app/dal/llm/`)

**Ported from AiSummryIO essentially unchanged.** An OpenAI-compatible JSON-mode
client. Default target is a local model through Ollama, but the same code works
against OpenAI itself, vLLM, Groq, and other compatible gateways.

Model, API key, and base URL are read from the runtime settings store on **every
call**, so a change saved in the UI applies immediately without a restart.

## Files

| File | Role |
|---|---|
| `openai_client.py` | `OpenAIJsonClient` — the only class callers use |
| `completion_retry.py` | Transient-failure retry around one API call |
| `json_response_parser.py` | `extract_json` — strips fences, finds the object |
| `message_merger.py` | Folds the system prompt into the user turn |
| `model_id_extractor.py` | Pulls model IDs out of a `/models` response |

Each helper is separate because each handles a different failure of
"OpenAI-compatible" servers that are only approximately compatible.

## `complete_json(system, user, schema=None) -> dict`

The one method that matters. Returns a parsed JSON object, adding a `_usage` key
with token counts when the server reports them.

Two robustness layers stack:

**1. The degradation ladder** (`_attempts`) — tried in order, dropping to the next
on `BadRequestError`:

1. `response_format: json_schema` with the caller's schema
2. `response_format: json_object` (plain JSON mode)
3. no `response_format` at all
4. same, but with the system prompt merged into the user turn — some local
   deployments reject a `system` role outright

Only a `BadRequestError` advances the ladder; any other exception becomes an
`AgentError` immediately.

**2. The parse retry** — if the reply is not valid JSON, the bad reply and a
correction instruction are appended and the ladder runs once more. Two failures
raise an `AgentError` in Hebrew.

`llm_diet_mode` caps completion tokens.

## Connection reuse

`_client_for(api_key, base_url)` caches one `OpenAI` client keyed by
`(api_key, base_url)`. A fresh client per call paid a TCP/TLS handshake on every
round-trip. The cache re-keys automatically when settings change mid-session,
because the store is still read per call.

## Local-server accommodations

- **No API key is required when `llm_base_url` is set.** Local servers ignore
  auth; the SDK still demands a non-empty string, so a placeholder is sent.
- `list_models()` calls `/models` over raw `httpx` rather than the SDK, so the
  admin UI can probe a candidate endpoint before saving it.
- Base URLs are normalized before storage: a pasted `.../chat/completions` has the
  operation suffix stripped, because the SDK appends the path itself and would
  otherwise 404.

## Rules

- Errors leaving this package are `AgentError` in Hebrew.
- Never log API keys, or full prompts containing employee personal details.
- Adding a rung to the ladder means adding it to `_attempts` — do not scatter
  fallback logic through `_complete`.
- **Nothing in `bl/audit.py` may call this.** The audit is arithmetic precisely so
  it cannot be hallucinated ([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
