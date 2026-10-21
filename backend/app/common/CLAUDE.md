# Common (`app/common/`)

Cross-cutting infrastructure. **Ported from AiSummryIO.**

- `config.py` — env-derived defaults, prefix **`PAKASH_`**, read from
  `.env`. These are *defaults*; the runtime store overrides them.
- `runtime_settings/` — the live override store. Settings saved in the UI beat env
  values **without a restart**, because `dal/llm/` reads the store on every call.
  Secrets are masked on the way out; a masked value coming back means "unchanged",
  so the stored secret is kept.
- `sessions.py` — signed workspace session cookies: `issue()` and `read()`,
  HMAC-SHA256 over a compact payload. Not a JWT and not trying to be — no
  algorithm field, no library, a format this file fully controls.
- `logging_setup.py` — standard-library logging configuration.
- `errors.py` — `AgentError`, the Hebrew-facing error type everything raises.
- `throttle.py` — `LoginThrottle`: every password check (boss login,
  employee login, change password, settings password) runs through
  `attempt()`, which locks an account for 15 minutes after 5 wrong guesses.
  Keyed by account, not IP — behind the Next proxy every request has the same
  IP. Shared through the `login_attempts` table when handed the repository
  (D35); otherwise in memory, per process.
- `events.py` — `TeamEvents`: an employee route `publish()`es "the
  requests (or swaps) inbox moved" from its worker thread, and the manager's
  SSE stream, waiting on the event loop, wakes up (D29). No payload. Across
  processes over PostgreSQL LISTEN/NOTIFY (`dal/notify.py`), otherwise in
  memory; the client's 15-second poll is the backstop either way.
- `runtime_settings/` re-reads its file from `get()` at most every few
  seconds, so a save made by another process arrives without a restart.

## Settings that matter here

| Setting | Purpose |
|---|---|
| `PAKASH_LLM_MODEL` | The model id |
| `PAKASH_LLM_BASE_URL` | OpenAI-compatible endpoint; defaults to local Ollama |
| `PAKASH_LLM_MODEL_<ROLE>` | Optional model id for `FAST`, `DEFAULT`, or `ADVANCED` |
| `PAKASH_LLM_BASE_URL_<ROLE>` | Optional endpoint for that role; falls back to the general URL |
| `PAKASH_LLM_API_KEY_<ROLE>` | Optional API key for that role's endpoint; falls back to `OPENAI_API_KEY`. A role on another provider is authenticated by another credential |
| `PAKASH_LLM_DIET_MODE` | Compact prompts and bounded completions |
| `PAKASH_LLM_TIMEOUT_SECONDS` | Wall time for one logical call, retries included |
| `OPENAI_API_KEY` | Read unprefixed, as the SDK expects |
| `PAKASH_DATABASE_*` | URL plus optional explicit overrides |
| `PAKASH_SESSION_SECRET` | Signs the workspace session cookie. **Set this in production** — unset, it is generated per process, so sessions die on restart and break across workers. Changing it logs every boss out. |
| `PAKASH_SETTINGS_PASSWORD` | Unlocks the settings panel on top of the boss login, sent as the `X-Settings-Password` header. Defaults to `010802` (committed); **override it in any real deployment**. Set to empty, the panel stays locked. The settings are shared by every workspace, and anyone can open a workspace and be its boss |
| `PAKASH_SESSION_DAYS` | How long a boss stays logged in (default 30) |
| `PAKASH_SOLVER_TIME_LIMIT_SECONDS` / `PAKASH_SOLVER_WORKERS` | The constraint solver's wall time per solve (default 10s) and parallel workers (default 8). Live-editable in the panel |
| `PAKASH_LLM_MAX_CONCURRENCY` | Model calls in flight across every process (default 4; 1 for a local Ollama). One per team regardless |

## Rules

- Secrets are never returned by the API unmasked and never logged. That
  includes the session secret and `teams.member_token`.
- Session cookies are `HttpOnly` and `SameSite=lax`. `Secure` is set at the
  reverse proxy, not here — the app is served over plain HTTP on the local
  network this product targets, where a `Secure` cookie would simply never be
  stored and the login would appear to work while doing nothing.
- A setting the user can edit belongs in the runtime store, not only in env.
- `AgentError` messages are Hebrew — they reach a Hebrew-speaking boss directly.
