# Common (`app/common/`)

Cross-cutting infrastructure. **Ported from AiSummryIO.**

- `config/settings.py` — env-derived defaults, prefix **`PAKASH_`**, read from
  `.env`. These are *defaults*; the runtime store overrides them.
- `runtime_settings/` — the live override store. Settings saved in the UI beat env
  values **without a restart**, because `dal/llm/` reads the store on every call.
  Secrets are masked on the way out; a masked value coming back means "unchanged",
  so the stored secret is kept.
- `sessions.py` — signed workspace session cookies: `issue()` and `read()`,
  HMAC-SHA256 over a compact payload. Not a JWT and not trying to be — no
  algorithm field, no library, a format this file fully controls.
- `logging_setup.py` — `structlog` configuration.
- `errors.py` — `AgentError`, the Hebrew-facing error type everything raises.

## Settings that matter here

| Setting | Purpose |
|---|---|
| `PAKASH_LLM_MODEL` | The model id |
| `PAKASH_LLM_BASE_URL` | OpenAI-compatible endpoint; defaults to local Ollama |
| `PAKASH_LLM_DIET_MODE` | Compact prompts and bounded completions |
| `PAKASH_LLM_TIMEOUT_SECONDS` | Wall time for one logical call, retries included |
| `OPENAI_API_KEY` | Read unprefixed, as the SDK expects |
| `PAKASH_DATABASE_*` | URL plus optional explicit overrides |
| `PAKASH_SESSION_SECRET` | Signs the workspace session cookie. **Set this in production** — unset, it is generated per process, so sessions die on restart and break across workers. Changing it logs every boss out. |
| `PAKASH_SESSION_DAYS` | How long a boss stays logged in (default 30) |

## Rules

- Secrets are never returned by the API unmasked and never logged. That
  includes the session secret and `teams.member_token`.
- Session cookies are `HttpOnly` and `SameSite=lax`. `Secure` is set at the
  reverse proxy, not here — the app is served over plain HTTP on the local
  network this product targets, where a `Secure` cookie would simply never be
  stored and the login would appear to work while doing nothing.
- A setting the user can edit belongs in the runtime store, not only in env.
- `AgentError` messages are Hebrew — they reach a Hebrew-speaking boss directly.
