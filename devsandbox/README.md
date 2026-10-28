# devsandbox

A throwaway local stack: Postgres, the backend, and the frontend, wired to a
model running on your host.

It exists so the app can be exercised end to end without touching the real
`pakashagent_*` volumes or the ports a dev server may already hold. Everything
here is development-only and never part of a deployed image.

## Run it

From the **repository root** — the build contexts are relative to that:

```bash
docker compose -p pakash-sandbox -f devsandbox/docker-compose.sandbox.yml up --build
```

Then open <http://localhost:3200/admin>, sign in to the operator console
(the committed default password is `010802` unless `PAKASH_ADMIN_PASSWORD` or
`PAKASH_SETTINGS_PASSWORD` is set) and open a team; then sign in to it from
<http://localhost:3200>. There is no separate worker service here: the job
worker runs inside the backend process (`PAKASH_EMBEDDED_WORKER` defaults on).

Tear it down, volumes included:

```bash
docker compose -p pakash-sandbox -f devsandbox/docker-compose.sandbox.yml down -v
```

## What is where

| | Sandbox | Normal stack | AiSummryIO sandbox |
|---|---|---|---|
| Frontend | <http://localhost:3200> | 3000 | 3100 |
| Backend | <http://localhost:8100> | 8000 | 8000 |
| Postgres | `localhost:55433` | 5432 | 55432 |
| Project name | `pakash-sandbox` | `pakashagent` | `aisummry-sandbox` |
| Volumes | `sandbox-db`, `sandbox-settings` | `pakash-db`, `pakash-settings` | — |

Every host port is deliberately shifted so this stack can run beside a dev
server, a local Postgres, **and** the AiSummryIO sandbox without taking a
port from any of them. Only the host side moves: inside the compose network
the frontend still reaches the backend at `http://backend:8000`.

Override any of them if they still collide:

```bash
PAKASH_SANDBOX_FRONTEND_PORT=3300 \
PAKASH_SANDBOX_BACKEND_PORT=8200 \
PAKASH_SANDBOX_DB_PORT=55434 \
  docker compose -p pakash-sandbox -f devsandbox/docker-compose.sandbox.yml up
```

```bash
psql postgresql://pakash:pakash@localhost:55433/pakash
```

## The model

The model runs on your **host**, not in the compose network. The backend
reaches it through `pghost`, an alias for the host gateway — `host.docker.internal`
resolves to an unreachable IPv6 address from some images, which is why the
alias is used instead.

So with Ollama on the host, the default works as-is:

```bash
ollama serve
ollama pull gemma3:27b
```

Point it somewhere else by overriding either variable before `up`:

```bash
PAKASH_LLM_MODEL=gemma3:12b \
PAKASH_LLM_BASE_URL=http://pghost:11434/v1 \
  docker compose -p pakash-sandbox -f devsandbox/docker-compose.sandbox.yml up
```

Or change it at runtime in the operator console's **מערכת ← הגדרות המערכת**
(`/admin`) — saved settings
override the environment without a restart, and they persist on the
`sandbox-settings` volume across container rebuilds.

## Tests

The sandbox backend image installs the dev extras, so the suite runs in the
container against the real Postgres:

```bash
docker compose -p pakash-sandbox -f devsandbox/docker-compose.sandbox.yml \
  exec backend python -m pytest -q
```

## Notes

- `settings-permissions` is a one-shot `chown` that runs before the backend
  and exits. Docker creates the settings volume owned by root, but the
  backend runs as uid 999 and must write `runtime-settings.json` there; without
  it, saving the system settings fails. The uid appears in both that
  service and `backend.sandbox.Dockerfile` — change them together.
- The per-field `PAKASH_DATABASE_*` overrides are deliberately blanked. They
  default to `localhost`, which inside the backend container means the
  container itself, and they take precedence over `PAKASH_DATABASE_URL`.
- `BACKEND_URL` is a **build** arg for the frontend, not just a runtime
  variable: `next.config.ts` bakes the rewrite target into the build output.

## Scenarios

`scenarios/` holds ready-made teams for exercising edge cases. Each is a
profile JSON plus a Hebrew guide of what to try. Load one into a running
stack (it opens a new team and never touches an existing one):

```bash
python devsandbox/seed_scenario.py devsandbox/scenarios/unit_619.json \
    --url http://localhost:8100 --admin-password 010802 --team-password 619619
```

`backend/tests/test_scenarios.py` saves every scenario through the profile
validators, so one the schema has outgrown fails in CI rather than on the
evening someone sits down to use it.
