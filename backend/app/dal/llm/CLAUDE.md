# LLM client (`app/dal/llm/`)

Ported from AiSummryIO and extended. An OpenAI-compatible JSON-mode client.
The default target is a local model through Ollama, but the same code works
against OpenAI itself, vLLM, Groq, and other compatible gateways. It is used
for language only — translating a build's sentences, the manager chat,
the one-shot change agent, learning from corrections. **No schedule is assigned
through it** (D34).

Model, API key, and base URL are read from the runtime settings store on **every
call**, so a change saved in the UI applies immediately without a restart. All
three are per role, so different kinds of work can run on different providers.

## Files

| File | Role |
|---|---|
| `openai_client.py` | `OpenAIJsonClient` — the only class callers use |
| `ladder.py` | The degradation ladder, its rungs, `is_context_overflow`, the reasoning-effort fields |
| `budgets.py` | Read ceiling, connect timeout and total budget per flow |
| `team_context.py` | `model_team()` — the team the current call is charged to, for its team slot |
| `telemetry.py` | The one `pakash.llm` log line per logical call |
| `completion_retry.py` | Transient-failure retry with exponential backoff |
| `json_response_parser.py` | `extract_json` — strips fences, finds the object |
| `message_merger.py` | Folds the system prompt into the user turn |
| `model_id_extractor.py` | Pulls model IDs out of a `/models` response |
| `model_roles.py` | Flow → role → model id, endpoint and API key, and the fallbacks |
| `model_slots.py` | `ModelSlots` (one process) and `PostgresModelSlots` (advisory locks) — the concurrency limit across every process (D35) |
| `strict_schema.py` | A caller's schema in strict-mode form, and the reply read back in the caller's shape |
| `streaming.py` | One completion read as a stream, for callers passing `on_text`; a refused stream retries the same rung plainly |

Each helper is separate because each handles a different failure of
"OpenAI-compatible" servers that are only approximately compatible.

## `complete_json(system, user, schema=None, flow="", role="", model="") -> dict`

The one method that matters. Returns a parsed JSON object, adding a `_usage` key
with token counts when the server reports them.

Two robustness layers stack:

**1. The degradation ladder** (`ladder.attempts`) — tried in order, dropping to the next
on `BadRequestError`:

1. `response_format: json_schema` with `strict: true`, when the schema has a
   strict form (`strict_schema.py`): every property required, the optional
   ones nullable, no extra keys. The server decodes against it; the nulls
   are dropped from the reply so callers see the shape they always did. A
   schema with a free-form object has no strict form and skips this rung.
2. `response_format: json_schema` with the caller's schema
3. `response_format: json_object` (plain JSON mode)
4. no `response_format` at all
5. same, but with the system prompt merged into the user turn — some local
   deployments reject a `system` role outright

Only a `BadRequestError` advances the ladder; any other exception becomes an
`AgentError` immediately.

**The ladder starts where it last succeeded.** `OpenAIJsonClient` remembers,
per (endpoint, model, schema), the rung that answered, and the next call
starts there. A server that refuses `json_schema` refuses it every time, and
without the memory each call paid that 400 round-trip again before stepping
down. Keyed by the schema too, so one flow's schema being refused does not
cost another flow its structured output. It only ever moves down, and lives
per process: a restart, or a different endpoint or model in the settings,
starts from the top again.

**The clock closes the prompt.** `agent_time_context()` is appended to the
end of the user turn at minute precision, and a caller making several calls
for one request (the manager chat's rounds) passes `time_context=` to pin one
clock for all of them. Inference servers (Ollama, llama.cpp, vLLM with prefix
caching) and OpenAI's prompt caching reuse the computation for the part of a
prompt that is identical to the previous one. A clock ticking every second
made that part end right after the system prompt; one in the system prompt,
even per minute, still cut every later turn's prefix there. At the end it
costs only itself.

**A context-overflow 400 does not advance it.** A prompt longer than the
server's context window is also a `BadRequestError`, and no rung can shorten
it — every remaining one sends the same oversized messages, fails identically,
and buries the real cause behind whichever rung ran last. `ladder.is_context_overflow`
matches it on the error text (vLLM, Ollama and llama.cpp all answer 400 with
prose, none with a distinct code) and raises a Hebrew error naming the actual
problem. This matters more than it looks: on vLLM the context window is fixed
at server start by `--max-model-len` and there is no per-request override, so
"the prompt is too long" is a real and unfixable-from-here condition.

**2. The parse retry** — if the reply is not valid JSON, the bad reply and a
correction instruction are appended and the ladder runs once more. Two failures
raise an `AgentError` in Hebrew.

**An empty reply is a rejected reply, not an exception.** `response_data`
returns `""` with the usage rather than raising, so the empty reply goes
through the same retry, its tokens are added, and two in a row raise
`ModelOutputError(usage=...)` with a `FAILED` log line. Raising inside the
ladder lost the tokens: they reached neither the log nor `_usage`, and a
flow's cost read as zero for a call that was paid for. It is common, not
exotic — gpt-oss, trained on native tool calling, answers a prompt that
describes tools with `finish_reason=tool_calls` and empty `content` on
roughly a quarter to half of manager-chat rounds, on every rung. The retry's
correction (`_NO_CONTENT`) tells it not to call functions, which "not valid
JSON" would not.

`llm_diet_mode` caps completion tokens.

**`llm_reasoning_effort` is how long the model thinks** — most of the wait
on a reasoning model. Empty sends nothing. Otherwise `ladder._add_reasoning`
sends it in the family's form: `reasoning_effort` for gpt-oss and the
o-series (`off` is `low`; they cannot stop thinking), and
`extra_body.chat_template_kwargs.enable_thinking` for Qwen3 (`off`/`low`
turn thinking off). Chosen by the model id, because the field one family
needs is the field the other rejects.

**A harmony glitch is asked again, not stepped around.** gpt-oss on vLLM
answers 400 ("unexpected tokens remaining in message header") when the text
it sampled breaks its own message format. The request was fine, so the same
rung is asked up to twice more (`ladder._rung`) before the ladder moves on.

**`on_text` streams without changing the answer.** A caller passing it (the
manager chat, to show its reply as it is written) gets the raw text so far
after every chunk; the parsed object returned is the same. A 400 on the
streamed request — some compatible servers refuse `stream` or
`stream_options` — does not advance the ladder: the same rung is asked again
without a stream, and that endpoint and model are not asked to stream again
for the life of the process.

**Every call has a read ceiling (D38).** `llm_timeout_seconds` of 0 means
the built-in ceiling (300s; the scheduler's own 900s), never "forever": an
unanswered call used to hold its worker and model slot until a restart, and
every chat and build behind it read "ממתין למודל…". A read timeout is not
retried (`completion_retry._read_timed_out`), and the SDK's own silent
retries are off (`max_retries=0`), so a stuck call fails after one ceiling
and gives its slot back.

**3. The total budget** — `budgets.budget_seconds()` bounds one logical
`complete_json`. `llm_timeout_seconds` bounds a single HTTP round-trip, but
the ladder can run four of them and each retries up to three times; multiplied
out, one request could hold a worker for the better part of an hour. The
deadline is passed into `create_with_retry`, which starts no attempt (and
takes no sleep) that would cross it.

**The `scheduler` flow does not honour `llm_timeout_seconds`.**
`budgets.read_timeout_for()` gives it its own ceiling instead —
`_SCHEDULER_READ_CEILING_SECONDS` (15 minutes), or the setting if that is
larger — and `budget_seconds()` sizes its budget to let that one attempt
finish.

This is the one place a configured setting is deliberately not honoured.
`scheduler` is now the build's translation step (the `DirectiveAgent`), a
large prompt to the *advanced* model, while most other calls are short; a
timeout chosen so the chat feels responsive would cut translations off
mid-answer. It is bounded rather than unlimited because a call the server
never answers would otherwise hold its model slot forever, and the
manager's stop button does not interrupt an HTTP read. A translation that
times out does not fail the build: the solver builds without it and the
notes say so.

Connecting stays bounded for *every* flow (`budgets._CONNECT_TIMEOUT_SECONDS`, 30s): a
handshake that never completes is an unreachable server, not a slow one, and
no amount of waiting fixes it.

A timeout that does fire on another flow raises Hebrew naming the setting and
how to change it — "Request timed out." is not something a manager can act on.

## Task-based model routing

Three roles. A role names a model id and may name its own base URL and API key
in runtime settings. An empty role URL falls back to `llm_base_url` and an
empty role key to `openai_api_key`, so a deployment with one server is
unchanged. OpenAI clients are cached by `(key, URL, timeout)`; roles on the
same connection share a pool, while roles on different ones keep separate
pools — including two roles on the same URL with different keys, which must
never share a client or one would authenticate as the other.

| Role | Model setting | URL setting | Key setting | Flows |
|---|---|---|---|---|
| `advanced` | `llm_model_advanced` | `llm_base_url_advanced` | `llm_api_key_advanced` | `scheduler` (translating a build's sentences) |
| `default` | `llm_model_default` | `llm_base_url_default` | `llm_api_key_default` | `changes`, `planner`, `learn`, and anything unmapped |
| `fast` | `llm_model_fast` | `llm_base_url_fast` | `llm_api_key_fast` | (no active flow) |

**A key travels with the URL it authenticates, not with the process.** One
shared key stops being right the moment two roles sit on two providers: it is
either absent where a hosted API requires one, or sent to a server it does not
belong to. So each endpoint field has a key field beside it.

**The key falls back on its own, not as part of a pair.** A role naming its own
URL but no key still borrows the general key — a second Ollama on the LAN needs
the placeholder rather than a credential — and the client sends the placeholder
when both are empty, so a local endpoint is never blocked for want of a key it
ignores.

**`flow` routes.** The argument every caller already passed for telemetry is
what picks the role, so a caller names itself once. A second argument would be
a second thing to keep in step with the first. `role=` and `model=` override
it for a one-off; nothing in `bl/` needs either.

`scheduler` is the one advanced flow: the `DirectiveAgent` translating a
build's rules, policies and instructions into requests the solver honours
(D34). It no longer assigns anybody.

**An unset role falls back to `llm_model`.** That single `or` is the whole
backward-compatibility story: a deployment that never opens the new settings
sends exactly what it sent before, and a `runtime-settings.json` written
before these fields existed loads unchanged. Roles ship empty for the same
reason `ladder.attempts` sends no `repetition_penalty` at 0 — a default here would
be a hardcoded model name, and which models exist is the server's business.

**The model is resolved per call**, immediately before the request, so a
selection saved in the system settings applies to the next call without a
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

`PostgresModelSlots` bounds in-flight completions across the API and every
worker with session advisory locks (D35). `llm_max_concurrency` is read on
each acquisition, so a saved value applies to the next call without a
restart. Each call also holds one of its team's numbered locks;
`llm_team_concurrency` caps how many (0, the default, is the whole global
limit, so a team's chat never waits behind its own build). A dead process
loses both locks with its database session. Callers without database settings (small adapters and
unit tests) retain the priority-aware process-local `ModelSlots`.

The default is 4: a hosted API or a continuously-batching server (vLLM,
TGI) takes several calls at once and is *starved* by a low limit. A
one-request-at-a-time local server (Ollama's default) is only thrashed by a
high one and should be set to 1. A server that serves one request at a time
queues concurrent calls itself, and a queued call counts against the read
ceiling.

## Telemetry

`complete_json` logs one line per logical call to the `pakash.llm` logger:
flow, **role**, model, prompt/completion/total tokens, retries and wall
duration.

`role` sits beside `model` rather than replacing it: the role says which
setting was consulted, the model says what actually ran. Either alone cannot
tell a misrouted flow from a misconfigured role, which is the question these
lines get asked once more than one model is in play.

`flow` is what the `flow=` argument on `complete_json` exists for —
`scheduler`, `planner` (the manager chat), `changes`, `learn`. Without it every measurement
reads "some model call", and the first question anyone asks of the numbers is
which feature is the expensive one.

This was added because nothing recorded it: `_usage` came back from here and
no active flow reads it. "How many
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

`_client_for(api_key, base_url, timeout)` caches `OpenAI` clients keyed by
`(api_key, base_url, timeout)`. A fresh client per call paid a TCP/TLS handshake
on every round-trip. The cache picks up settings changes mid-session because
the store is still read per call. **The model is not part of the key**: models
on the same endpoint share one client and pool.

**The key is part of it, and has to be.** Two roles can name the same provider
with different credentials — one project's key for the scheduler and another's
for chat — and a cache keyed on the URL alone would hand the second role the
first one's client, silently billing and authenticating as the wrong account.

## Local-server accommodations

- **No API key is required when `llm_base_url` is set.** Local servers ignore
  auth; the SDK still demands a non-empty string, so a placeholder is sent.
- `list_models()` calls `/models` over raw `httpx` rather than the SDK, so the
  admin UI can probe a candidate endpoint before saving it. It takes a `role`,
  so an omitted URL or key falls back to *that role's* saved connection: with
  roles free to sit on different providers, the general endpoint's catalogue is
  the wrong list for a role pointing elsewhere.
- Base URLs are normalized before storage: a pasted `.../chat/completions` has the
  operation suffix stripped, because the SDK appends the path itself and would
  otherwise 404.

## Rules

- Errors leaving this package are `AgentError` in Hebrew.
- Never log API keys, or full prompts containing employee personal details.
- Adding a rung to the ladder means adding it to `ladder.attempts` — do not scatter
  fallback logic through `_complete`.
- Routing is `model_roles.py` and nowhere else. A flow gets a model by being
  in the table, not by a branch at the call site.
- Keep endpoint and credential routing beside model routing in
  `model_roles.py`; call sites name only their flow.
- **A role's key is never sent to another role's endpoint.** The resolution is
  per role in one place, and the client cache is keyed by the key as well as
  the URL so two roles on one provider with different keys stay separate.
- **Never fail over to another model.** See the routing section.
- **Nothing in `bl/audit/` may call this.** The audit is arithmetic precisely so
  it cannot be hallucinated ([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
