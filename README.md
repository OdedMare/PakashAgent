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
schedule. They can generate one date or any date range with persistent
per-day progress, drag a shift (which asks why before it
moves), talk to the agent about the assignment, record constraints against
employees, and publish to the team.

**The agent speaks first.** It reads the state on its own and opens the
conversation — when the manager arrives, after anything changes, before a
period is published, and periodically in an idle room. It says what it
noticed and offers the sentence that would act on it, but it still writes
nothing: the manager sends the sentence, the agent proposes, the manager
confirms with their reason
([D15](docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).

**The copilot stays awake when the browser closes.** A separate durable worker
checks every workspace, records profile gaps and schedule problems in a
manager inbox, retries failed work, and opens focused follow-up interviews.
Permissions are set per action type; every decision, verification and rollback
is recorded in an append-only audit trail
([D23](docs/DECISIONS.md#d23--the-copilot-is-durable-permissioned-and-reversible)).

**The agent answers questions, not only requests.** The manager can ask
*"מי יכול להחליף את יוסי בסופ״ש"* or *"מה חסר לפני פרסום"* and get an
answer assembled from deterministic tools — who is free, who is qualified,
what is unstaffed, what stands before publishing. The model picks which
questions to ask; `bl/tools.py` answers each with arithmetic, so the agent
cannot claim a placement is valid unless the check said so
([D19](docs/DECISIONS.md#d19--the-agent-answers-with-tools-asking-and-changing-stay-separate)).
An answer carries no operations: asking is not changing.

**A change can be simulated before it is made.** *"מה יקרה אם אעביר את דנה
לחמישי בערב"* returns what would break, what would clear, how coverage and
hours would move, and everyone affected — computed in memory, persisting
nothing. Approving it runs the ordinary confirm-with-a-reason path
([D20](docs/DECISIONS.md#d20--a-simulation-is-not-a-proposal)).

**All of that works with no model configured.** The same tools run, driven
by a deterministic reader of the manager's Hebrew instead of by the model.
It covers six question shapes and says plainly when it did not understand
one, rather than guessing.

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
and imported back. A message for the group chat is asked of the agent instead
— it is writing, and writing here is the agent's job
([D17](docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).

Built: the ported `dal/llm` client, settings and runtime settings, the interview
and its prompt, the workspace layer (teams, boss login, member share links, route
guards), `bl/audit.py` and its table-driven tests, `bl/scheduler.py`,
`bl/changes.py`, `bl/briefing.py`, `bl/export.py`, `bl/placement.py`, the agent's
tool layer (`bl/tools.py`, `bl/planner.py`, `bl/intent.py`, `bl/simulate.py`),
the schedule tables, the management HTTP layer, and the RTL UI for all of it.

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
docker compose up          # backend, copilot worker, frontend, postgres
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
`PAKASH_LLM_MODEL` to point elsewhere. Fast, default, and advanced roles may
override both with `PAKASH_LLM_MODEL_<ROLE>` and
`PAKASH_LLM_BASE_URL_<ROLE>`. Nothing here is OpenAI-specific.
