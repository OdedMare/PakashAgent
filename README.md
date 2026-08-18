# PakashAgent

An agent that builds and maintains work shift schedules through conversation.

The boss teaches the agent the workplace once, in an intro interview. After that
the agent builds schedules, absorbs schedules the boss already has (Excel or
docs), and rearranges them on request — always explaining what it did and why.
Employees see the result; they do not edit it.

**Each team gets its own workspace.** The boss logs in with a password; team
members open a read-only view through a share link, with no account at all
([D10](docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).

**Hebrew, right-to-left.** Not just the UI — shift names, weekdays, availability
markers, and errors are all Hebrew. See [`backend/app/bl/CLAUDE.md`](backend/app/bl/CLAUDE.md).

## Status

**The intro interview works end to end.** The boss opens the app, answers one
question per turn (a selectable answer or their own words), and reaches a
confirmed workplace profile stored in Postgres.

**Workspaces work end to end.** A boss opens a team, gets a share link for the
employees, and everything they author is scoped to that team.

**The management area works end to end.** Once the interview is done the manager
lands in a control room holding the shift calendar, the roster and its
constraints, and a conversation with the agent about the current and future
schedule. They can generate a week, drag a shift (which asks why before it
moves), talk to the agent about the assignment, record constraints against
employees, and publish to the team.

**The agent speaks first.** It reads the state on its own and opens the
conversation — when the manager arrives, after anything changes, before a
period is published, and periodically in an idle room. It says what it
noticed and offers the sentence that would act on it, but it still writes
nothing: the manager sends the sentence, the agent proposes, the manager
confirms with their reason
([D15](docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).

Built: the ported `dal/llm` client, settings and runtime settings, the interview
and its prompt, the workspace layer (teams, boss login, member share links, route
guards), `bl/audit.py` and its table-driven tests, `bl/scheduler.py`,
`bl/changes.py`, `bl/briefing.py`, the schedule tables, the management HTTP
layer, and the RTL UI for all of it.

Not built yet: `bl/importer.py` and the import-confirmation screens — see
[`docs/BUILD_ORDER.md`](docs/BUILD_ORDER.md) step 6.

Every architectural decision was settled in a design interview and is recorded —
with its reasoning — in [`docs/DECISIONS.md`](docs/DECISIONS.md). Read that before
writing code; several decisions are counterintuitive and one is a deliberate,
accepted tradeoff.

## The four steps the product exists to serve

1. **Intro interview** — the agent asks about the job, the employees, the shift
   structure, dependencies, and the mission. This is where the workplace's own
   shift vocabulary is collected (every workplace names shifts differently).
2. **The boss loads shifts** — or asks the agent to generate them. Both are
   supported and land in the same representation.
3. **Import from Excel/docs** — real files vary structurally. The agent infers
   the layout and shows its reading for confirmation before committing.
4. **Conversational changes** — "Dana's sick Thursday." The agent asks why if the
   boss didn't say, proposes a replacement with its reasoning, and applies it on
   confirmation.

## Architecture at a glance

```
backend/          FastAPI + Postgres, layered api / bl / dal
  app/api/        HTTP contracts and routers
  app/bl/         Decisions: interview, scheduling, changes, audit, import
  app/dal/        Data access: Postgres, LLM client
  app/common/     Config, runtime settings, logging, errors
frontend/         Next.js, RTL, chat-first with a schedule grid
```

Ported from [OdedMare/AiSummryIO](https://github.com/OdedMare/AiSummryIO): the
whole `dal/llm` package (an OpenAI-compatible JSON client that also works against
Ollama, vLLM, and Groq), settings, runtime settings, the markdown prompt loader,
and the repository base. See [`backend/CLAUDE.md`](backend/CLAUDE.md).

## Running it

```bash
docker compose up          # backend, frontend, postgres
```

Running the two halves directly instead:

```bash
cd backend
python -m pytest -q
uvicorn app.main:app --reload          # :8000
```

```bash
cd frontend
npm install
npm run dev                            # :3000, proxies /api to the backend
```

Then open <http://localhost:3000>, create a team, and start the interview.
Finishing it opens the management area, where "בניית סידור לשבוע" generates a
week. The share button in the header reveals the link employees open
(`/team/<token>`); it grants a read-only view and no password, and shows only
schedules the manager has published.

Postgres must be reachable at `PAKASH_DATABASE_URL`; the app creates its own
tables on startup (the schema itself must already exist).

**Set `PAKASH_SESSION_SECRET` in any real deployment.** Left unset it is
generated per process, so sessions do not survive a restart and break across
workers.

The model defaults to a local Ollama endpoint; set `PAKASH_LLM_BASE_URL` and
`PAKASH_LLM_MODEL` to point elsewhere. Nothing here is OpenAI-specific.
