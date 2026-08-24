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
| `completion_retry.py` | Transient-failure retry with exponential backoff |
| `json_response_parser.py` | `extract_json` — strips fences, finds the object |
| `message_merger.py` | Folds the system prompt into the user turn |
| `model_id_extractor.py` | Pulls model IDs out of a `/models` response |
| `model_roles.py` | Flow → role → model id, and the fallback |

Each helper is separate because each handles a different failure of
"OpenAI-compatible" servers that are only approximately compatible.

## `complete_json(system, user, schema=None, flow="", role="", model="") -> dict`

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

**A context-overflow 400 does not advance it.** A prompt longer than the
server's context window is also a `BadRequestError`, and no rung can shorten
it — every remaining one sends the same oversized messages, fails identically,
and buries the real cause behind whichever rung ran last. `_is_context_overflow`
matches it on the error text (vLLM, Ollama and llama.cpp all answer 400 with
prose, none with a distinct code) and raises a Hebrew error naming the actual
problem. This matters more than it looks: on vLLM the context window is fixed
at server start by `--max-model-len` and there is no per-request override, so
"the prompt is too long" is a real and unfixable-from-here condition.

**2. The parse retry** — if the reply is not valid JSON, the bad reply and a
correction instruction are appended and the ladder runs once more. Two failures
raise an `AgentError` in Hebrew.

`llm_diet_mode` caps completion tokens.

**3. The total budget** — `_TOTAL_BUDGET_SECONDS` bounds one logical
`complete_json`. `llm_timeout_seconds` bounds a single HTTP round-trip, but
the ladder can run four of them and each retries up to three times; multiplied
out, one request could hold a worker for the better part of an hour. The
deadline is passed into `create_with_retry`, which starts no attempt (and
takes no sleep) that would cross it.

The `scheduler` flow uses a shorter 120-second logical budget. Its interactive
path checkpoints one date per request, so retrying that date is cheaper and
more honest than making the whole range look frozen for five minutes.

## Task-based model routing

Three roles. A role names a model id and may name its own base URL in runtime
settings. An empty role URL falls back to `llm_base_url`, so a deployment with
one server is unchanged. OpenAI clients are cached by connection; roles on the
same URL share a pool, while roles on different URLs keep separate pools.

| Role | Model setting | URL setting | Flows |
|---|---|---|---|
| `advanced` | `llm_model_advanced` | `llm_base_url_advanced` | `scheduler` |
| `default` | `llm_model_default` | `llm_base_url_default` | `interview`, `changes`, `planner`, `learn`, and anything unmapped |
| `fast` | `llm_model_fast` | `llm_base_url_fast` | `briefing` |

**`flow` routes.** The argument every caller already passed for telemetry is
what picks the role, so a caller names itself once. A second argument would be
a second thing to keep in step with the first. `role=` and `model=` override
it for a one-off; nothing in `bl/` needs either.

`scheduler` is the one advanced flow — it reasons over a whole period of
slots, people and rules at once, and it is the call the product is judged on.
`briefing` is a few sentences over facts `audit.py` already computed.

**An unset role falls back to `llm_model`.** That single `or` is the whole
backward-compatibility story: a deployment that never opens the new settings
sends exactly what it sent before, and a `runtime-settings.json` written
before these fields existed loads unchanged. Roles ship empty for the same
reason `_attempts` sends no `repetition_penalty` at 0 — a default here would
be a hardcoded model name, and which models exist is the server's business.

**The model is resolved per call**, immediately before the request, so a
selection saved in the settings panel applies to the next call without a
restart — the property the base URL and key already had.

**No automatic failover.** A timeout, a 5xx, or an invalid reply never
switches model. The retry curve and the ladder both stay on the resolved
model: a generation that timed out may still be running on the server, and
re-sending it to a second model duplicates the work and makes the outcome
depend on which one answers first.

## Retry and backoff

`completion_retry.py` retries `RateLimitError`, `APIConnectionError`,
`APITimeoutError` and `InternalServerError` — the last because a local server
out of KV cache or mid-model-load answers 5xx, which is transient in exactly
the way this retry is for. `BadRequestError` is never retried; that is the
ladder's job.

The delay is geometric with full jitter, capped at 8s. The original flat 0.3s
came from a hosted API, where a 429 means "too many per minute" and a short
pause genuinely clears it. **The local servers this actually runs against
behave differently:** a busy vLLM or Ollama does not reject a request, it
*queues* it, and the failure surfaces as `APITimeoutError` only after the full
timeout has already elapsed. Retrying 0.3s later hits a server still working
through the same queue. The jitter matters because several workers waiting on
one model server tend to time out together — one long generation blocks
everybody — and without it they would retry in lockstep and rebuild the pileup.

A `Retry-After` header is obeyed over the curve: the server knows when it will
be ready and the backoff is a guess.

## Concurrency

`_LLM_SLOTS` bounds in-flight completions process-wide, sized from
`llm_max_concurrency` on first use. It is built once and **cannot be resized**,
so unlike every other LLM setting this one takes effect at process start
rather than on save — the alternative is a UI control that silently does
nothing.

The right value depends entirely on the server, which is why there is no good
default:

- **A continuously-batching server (vLLM, TGI)** does its own scheduling and is
  *starved* by a low limit — a request held back here is a request it cannot
  put in a batch. 16+ suits those.
- **A one-request-at-a-time server (Ollama's default)** is only thrashed by a
  high one. 1-2 keeps latency honest.

The shipped default is 1 because the shipped endpoint is Ollama. Deployments
using a continuously-batching server should raise it explicitly.

## Telemetry

`complete_json` logs one line per logical call to the `pakash.llm` logger:
flow, **role**, model, prompt/completion/total tokens, retries and wall
duration.

`role` sits beside `model` rather than replacing it: the role says which
setting was consulted, the model says what actually ran. Either alone cannot
tell a misrouted flow from a misconfigured role, which is the question these
lines get asked once more than one model is in play.

`flow` is what the `flow=` argument on `complete_json` exists for —
`scheduler`, `interview`, `changes`, `briefing`. Without it every measurement
reads "some model call", and the first question anyone asks of the numbers is
which feature is the expensive one.

This was added because nothing recorded it: `_usage` came back from here and
only `bl/interview.py` ever read it, and even that dropped it. "How many
tokens does a schedule cost" had no answer, so every performance decision was
an estimate.

**Counts and timings only — never the prompt, the reply, or any part of
either.** Those carry employee names, stated reasons for absence, and the
manager's own sentences about their staff. Token counts describe the call
without describing anybody.

The failed path is logged too, marked `FAILED`: a call that spent tokens and
then failed is exactly the one worth seeing. `retries` is broken out because a
call that silently took two attempts costs double and is identical to a clean
one in every other metric.

## Connection reuse

`_client_for(api_key, base_url)` caches `OpenAI` clients keyed by
`(api_key, base_url, timeout)`. A fresh client per call paid a TCP/TLS handshake
on every round-trip. The cache picks up settings changes mid-session because
the store is still read per call. **The model is not part of the key**: models
on the same endpoint share one client and pool.

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
- Routing is `model_roles.py` and nowhere else. A flow gets a model by being
  in the table, not by a branch at the call site.
- Keep endpoint routing beside model routing in `model_roles.py`; call sites
  name only their flow.
- **Never fail over to another model.** See the routing section.
- **Nothing in `bl/audit.py` may call this.** The audit is arithmetic precisely so
  it cannot be hallucinated ([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
