# Common (`app/common/`)

Cross-cutting infrastructure. **Ported from AiSummryIO.**

- `config/settings.py` — env-derived defaults, prefix **`PAKASH_`**, read from
  `.env`. These are *defaults*; the runtime store overrides them.
- `runtime_settings/` — the live override store. Settings saved in the UI beat env
  values **without a restart**, because `dal/llm/` reads the store on every call.
  Secrets are masked on the way out; a masked value coming back means "unchanged",
  so the stored secret is kept.
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

## Rules

- Secrets are never returned by the API unmasked and never logged.
- A setting the user can edit belongs in the runtime store, not only in env.
- `AgentError` messages are Hebrew — they reach a Hebrew-speaking boss directly.
