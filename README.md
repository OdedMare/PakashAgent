# משמרות זהב

*Golden Shifts — codebase name `PakashAgent`; env vars, storage keys and the
database keep the `pakash` prefix.*

An agent that builds and maintains work shift schedules through conversation.

The boss defines the workplace once in a structured, zero-token setup form.
After that a constraint solver builds schedules, and the agent rearranges
them on request in a conversation — always explaining what it did and why.
Employees see the result and submit constraint requests and swaps; they do
not edit it. A schedule kept in a spreadsheet can be imported, in any
layout, and the manager confirms what was read before anything is stored (D42).

**Each team gets its own workspace**, opened by the operator in the
צוות משמרות זהב console at `/admin` ([D28](docs/DECISIONS.md)). The boss logs
in with a password; team members open a read-only view through a share link,
with no account at all, and may claim their name to reach a personal area
([D10](docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).

**Hebrew, right-to-left.** Not just the UI — shift names, weekdays, availability
markers, and errors are all Hebrew. See [`backend/app/bl/CLAUDE.md`](backend/app/bl/CLAUDE.md).

## Status

**Unit setup works end to end without a model call.** The boss defines the
roster, shifts, rotations and rules in a structured form saved in Postgres.

**A מכלול works end to end** ([D43](docs/DECISIONS.md)). צוות משמרות זהב
joins existing teams — each a **משמרת** with its own **מפקד משמרת** — under a
**מפקד מכלול**, whose password only the operator issues. The commander sees
every משמרת on one board, narrows it to one משמרת and one shift type, and
enters any משמרת with all of its commander's tools; every change they make
there is told to that משמרת's commander.

**Workspaces work end to end.** A boss opens a team, gets a share link for the
employees, and everything they author is scoped to that team.

**The management area works end to end.** Once setup is done the manager
lands in a control room holding the shift calendar, the roster and its
constraints, and a conversation with the agent about the current and future
schedule. They can generate one date or any date range with persistent
per-day progress, drag a shift (which asks why before it
moves), talk to the agent about the assignment, record constraints against
employees, and publish to the team.

**A constraint solver builds the schedule; the model only translates.**
OR-Tools CP-SAT assigns a whole span (up to four weeks) at once: every
availability, rotation, rest, run-of-days, weekly-hours and staffing rule,
the roles allowed on each shift, every structured request, an even share
of shifts and nights, and the longest rest between one person's shifts.
Trainees (נחפפים) are placed beside a trainer without taking a seat. A build
can cover any run of days and only some shift types. The model
turns the manager's free-text rules and instructions into those structured
requests; anything it cannot translate is named in the build's notes
rather than silently dropped
([D34](docs/DECISIONS.md)).

**A new soldier or shift joins the board already built.** Saving one in
setup, or in the changes tab ("שינויים": החלפת משמרת / הוספת חייל /
הוספת משמרת), refits every draft ahead of today and moves only what evening
the load needs; published weeks are left alone ([D37](docs/DECISIONS.md)).

**Work keeps running when the browser closes.** Builds, chat turns and
translations are durable jobs in PostgreSQL, claimed once and retried by a
worker that runs inside the API or on its own
([D23](docs/DECISIONS.md#d23--the-copilot-is-durable-permissioned-and-reversible)).

**The agent answers questions, not only requests.** In the manager chat,
*"מי יכול להחליף את יוסי בסופ״ש"* or *"מה חסר לפני פרסום"* is answered from
deterministic tools — who is free, who is qualified, what is unstaffed, what
stands before publishing. The model picks which questions to ask;
`bl/tools/` answers each with arithmetic, so the agent cannot claim a
placement is valid unless the check said so
([D19](docs/DECISIONS.md#d19--the-agent-answers-with-tools-asking-and-changing-stay-separate)).
An answer carries no operations: asking is not changing.

**A change can be simulated before it is made.** *"מה יקרה אם אעביר את דנה
לחמישי בערב"* returns what would break, what would clear, how coverage and
hours would move, and everyone affected — computed in memory, persisting
nothing. Approving it runs the ordinary confirm-with-a-reason path
([D20](docs/DECISIONS.md#d20--a-simulation-is-not-a-proposal)).

**The commonest requests need no model.** "מי יכול להחליף…" is answered by
a deterministic reader of the manager's Hebrew over the same tools, and a
plain absence ("עודד חולה בשני ושלישי") is read and planned in code with the
fairest cover ([D36](docs/DECISIONS.md)). The reader knows seven question
shapes and says plainly when it did not understand one, rather than guessing.
Building a schedule from structured input needs no model either.

**The agent remembers what it is told to.** Standing operational preferences
— *"עדיף לשאול את יוסי לפני רון לסופ״ש"* — are stored per team, visible,
editable, and never authorise a write. One the agent proposes stays inert
until the manager approves it
([D21](docs/DECISIONS.md#d21--the-agent-remembers-preferences-and-every-one-of-them-is-visible)).

**Employees are told what changed.** Someone with a claimed identity opens
their personal area and sees, first, what moved since they last looked — with
the manager's reason attached. Pressing "ראיתי" is what marks it read
([D16](docs/DECISIONS.md#d16--an-employee-is-told-what-changed-and-acknowledging-is-what-marks-it-read)).

**A schedule can leave.** The manager downloads the period as an Excel file
laid out like the real source sheets, so a week can be edited outside the app
and imported back. Import reads a file in any shape — shifts or people as
rows, dates across or down, weekday templates, stacked weeks — finding the
layout in code, asking the model to describe it only when unsure, and
letting the manager correct it before anything is stored
([D42](docs/DECISIONS.md)). A message for the group chat is asked of the agent instead
— it is writing, and writing here is the agent's job
([D17](docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).

Built: the ported `dal/llm` client, settings and runtime settings, structured
unit setup, the workspace layer (teams, boss login, member share links, route
guards, the operator console), `bl/audit/` and its table-driven tests,
`bl/scheduler/` and the `bl/solver/` constraint solver, `bl/changes/`,
`bl/export.py`, `bl/placement/`, the agent's tool layer (`bl/tools/`,
`bl/intent/`, `bl/absence/`, `bl/simulate/`), the manager chat, the employee
area, the schedule tables, the management HTTP layer, and the RTL UI for all
of it — with the two animated guards who greet visitors, stand in for the
agent and narrate the guide.

Every architectural decision was settled in a design interview and is recorded —
with its reasoning — in [`docs/DECISIONS.md`](docs/DECISIONS.md). Read that before
writing code; several decisions are counterintuitive and one is a deliberate,
accepted tradeoff.

## The three steps the product exists to serve

1. **Unit setup** — the boss defines employees, the workplace's own shift
   vocabulary, rotations, dependencies and rules in a structured form.
2. **The boss places shifts by hand** — or has the solver build them. Both
   land in the same representation.
3. **Conversational changes** — "Dana's sick Thursday." The agent asks why if the
   boss didn't say, proposes a replacement with its reasoning, and applies it on
   confirmation.

The shift board now has one persistent manager chat for questions, replacement
plans, weekly scheduling, employee management and rule updates. Recommendations
show concrete changes and rule conflicts before the manager clicks Apply.
See [Manager chat](docs/MANAGER_CHAT.md) for supported actions and approval behavior.

## Architecture at a glance

```
backend/              FastAPI + Postgres, layered api / bl / dal
  app/api/            HTTP contracts and routers
  app/bl/             Decisions: profiles, the solver, changes, audit
  app/bl/solver/      OR-Tools CP-SAT: who works which shift
  app/dal/            Data access: Postgres (data, throttle, live signals, model slots), LLM client
  app/common/         Config, runtime settings, logging, errors
frontend/             Next.js, RTL, chat-first with a schedule grid
```

Ported from [OdedMare/AiSummryIO](https://github.com/OdedMare/AiSummryIO): the
whole `dal/llm` package (an OpenAI-compatible JSON client that also works against
Ollama, vLLM, and Groq), settings, runtime settings, the markdown prompt loader,
and the repository base. See [`backend/CLAUDE.md`](backend/CLAUDE.md).

## Running it

```bash
docker compose up          # backend, job worker, frontend, postgres
```

Compose runs four API processes beside one worker and a tuned PostgreSQL.
For many teams at once -- sizing processes and connections, and finding the
slow query -- see [`docs/SCALING.md`](docs/SCALING.md).

Running the two halves directly instead:

```bash
cd backend
python -m pytest -q
uvicorn app.main:app --reload                 # :8000
```

```bash
cd frontend
npm install
npm run dev                            # :3000, proxies /api to the backend
```

Then open <http://localhost:3000/admin>, sign in with the operator password
(`PAKASH_ADMIN_PASSWORD`, else `PAKASH_SETTINGS_PASSWORD`), and open a team.
Sign in to it from <http://localhost:3000> and complete unit setup. Saving it
opens the management area, where an unbuilt week offers to be built (or
"בנייה מכאן" on any day's column). The share button in the header reveals the link employees open
(`/team/<token>`); it grants a read-only view and no password, and shows only
schedules the manager has published.

Postgres must be reachable at `PAKASH_DATABASE_URL`; the app creates its own
tables on startup (the schema itself must already exist).

**The solver has two settings.** The operator console's *מערכת ← הגדרות
המערכת ← בניית סידור* sets its wall time per solve (`PAKASH_SOLVER_TIME_LIMIT_SECONDS`, default 10) and its
parallel workers (`PAKASH_SOLVER_WORKERS`, default 8). It solves coverage
first and then, without giving any of it back, wishes and fairness; a seat
nobody can legally fill is reported, never refused. Every build records its
duration, solver status, model calls for translation (often none), tokens,
coverage, warnings and per-person load. To compare saved outputs against the
same profile, constraints and dates:

```bash
cd backend
.venv/bin/python -m app.bl.scheduler.compare \
  ../docs/scheduler-comparison.example.json --output /tmp/scheduler-comparison.json
```

**PostgreSQL is the only stateful service.** The login throttle, the
manager's live inbox (LISTEN/NOTIFY) and the model-call limit
(`PAKASH_LLM_MAX_CONCURRENCY`, default 4; set 1 for a local Ollama) all go
through it ([D35](docs/DECISIONS.md)). There is no Redis, and nothing calls
out but the model server (Opik tracing was removed for air-gapped networks).
A team may use every model slot unless `PAKASH_LLM_TEAM_CONCURRENCY` caps it;
`PAKASH_LLM_TIMEOUT_SECONDS=0` is a built-in ceiling (300s, builds 900s), so a
hung call fails instead of holding its slot ([D38](docs/DECISIONS.md)). See
[`backend/.env.example`](backend/.env.example) for every setting.

**Several replicas need nothing extra** ([D39](docs/DECISIONS.md)). Run
as many API pods as you like behind one Service, and as many frontend pods
(each built with `BACKEND_URL` pointing at that Service; it is baked in at
build time). What they must agree on goes through PostgreSQL:

- **The session key.** `PAKASH_SESSION_SECRET` when set; otherwise one key
  is generated and kept in the database, so every pod and every restart
  signs with it. Setting it yourself is still the cleaner choice.
- **Panel settings.** A save on one pod reaches every other within seconds,
  without a shared volume. The database connection itself stays in each
  pod's environment.
- **Jobs.** Each API pod runs the job worker in-process by default (six
  lanes, each build using `PAKASH_SOLVER_WORKERS` threads); a job is claimed
  once whichever pod picks it up. Size CPU limits for that, or set
  `PAKASH_EMBEDDED_WORKER=false` and run `python -m app.worker` as its own
  Deployment.

Give the ingress a read timeout of at least ten minutes: a model-backed
request may take five, and the frontend proxy allows ten.

The model defaults to a local Ollama endpoint; set `PAKASH_LLM_BASE_URL` and
`PAKASH_LLM_MODEL` (and `OPENAI_API_KEY`) to point at a hosted API. Structured
outputs are requested in strict mode first and degrade gracefully on servers
that refuse it. Fast, default, and advanced roles may
override them with `PAKASH_LLM_MODEL_<ROLE>`, `PAKASH_LLM_BASE_URL_<ROLE>`
and `PAKASH_LLM_API_KEY_<ROLE>`; `PAKASH_LLM_REASONING_EFFORT` bounds how
long a reasoning model (gpt-oss, Qwen3) thinks. Nothing here is
OpenAI-specific.
