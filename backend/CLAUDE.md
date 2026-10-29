# PakashAgent backend context

Read this before changing `backend/`.

Design decisions with their reasoning: [`../docs/DECISIONS.md`](../docs/DECISIONS.md).
Real Excel layouts: [`../docs/FILE_FORMATS.md`](../docs/FILE_FORMATS.md).

## Purpose

Turn a conversation with the boss into a maintained shift schedule. The
manager describes the workplace once in a structured setup form; a
constraint solver builds schedules from it (D34); the agent translates the
manager's sentences, answers questions and proposes changes in a
conversation — explaining every decision and recording every reason.

## Runtime and commands

Python is **3.11** (it was 3.8.10 until [D30](../docs/DECISIONS.md#d30--model-calls-are-traced-to-opik-prompts-and-replies-included)).
The code still writes `Optional`, `List`, `Dict`; match the file you are in.

```bash
cd backend
python -m pytest -q
uvicorn app.main:app --reload
```

## Architecture

- `common/` — env defaults (`PAKASH_` prefix) plus the live runtime-settings
  override store. Saved settings override env without restart; secrets masked.
- `dal/database.py` — connection; verifies the schema exists.
- `dal/llm/` — the OpenAI-compatible JSON client and its degradation ladder
  (strict structured outputs first). Model/base URL/API key stay live per
  call; concurrency is held with PostgreSQL advisory locks.
- `dal/notify.py` — LISTEN/NOTIFY between processes (D35).
- `dal/repository/` — the only SQL owner. `teams.py` also owns password
  hashing (`scrypt`, stdlib) and the member share token; `throttle.py` the
  shared login-attempt counts (D35).
- `bl/workspace_service.py` — workspace rules: who may enter a team, in which
  role, and what a new workspace inherits.
- `bl/admin_service.py` — the צוות משמרות זהב operator console (D28): opening,
  suspending and deleting teams. `dal/repository/admin.py` holds its
  cross-team queries — the one deliberate exception to team scoping.
- `api/dependencies.py` — the route guards (`visitor`, `boss`,
  `employee`, `admin`). `visitor` also refuses a suspended or deleted team.
- `common/sessions.py` — signed session cookies (HMAC-SHA256, no library).
- `common/events.py` — "an inbox moved" signals per team (across processes
  over PostgreSQL LISTEN/NOTIFY, `dal/notify.py`, D35), feeding
  the manager's SSE stream (`api/routers/employee/live.py`, D29). Signals
  carry no data; the screen re-reads through the guarded routes.
- `bl/profile_service/` — unit setup: the structured profile form (roster,
  shift vocabulary, staffing, rotations, rules, policies), validated and
  normalised in code with no model call. Saving queues the translation of
  its sentences (`compile_sources`, D32). There is no intro interview any
  more; a profile created here is `complete`, and an older partial one still
  reports its gaps through `profile_gaps`
  ([D22](../docs/DECISIONS.md#d22--the-interview-can-be-ended-early-and-the-profile-says-what-it-owes-️-amends-d18)).
- `bl/scheduler/` — builds a span: the slot grid (arithmetic), the
  manager's sentences translated by `bl/directive_agent/`, then the solver.
- `bl/solver/` — **the OR-Tools CP-SAT constraint solver that assigns every
  schedule** ([D34](../docs/DECISIONS.md)). One boolean per legal (person,
  slot); the audit's blocking checks and every hard request are
  constraints; coverage is solved first, then wishes and fairness. Every
  row carries a reason. No model call.
- `bl/directive_agent/` + `bl/compiled_sources/` — the model's one job in a
  build: translating rules, policies, notes, preferences and the build's
  instruction into structured requests (`bl/schedule_requests.py`), kept
  per sentence so a standing rule is translated once (D32). What does not
  translate is named in the build's notes.
- `bl/manager_chat.py` + `bl/chat_*.py` — **the agent.** One persistent
  conversation per manager: questions answered with read-only tools,
  replacement plans, generation previews, profile and constraint changes.
  A turn prepares a plan and writes nothing; `chat_apply.py` applies it on
  the manager's approval, atomically, after checking nothing moved.
- `bl/changes/` — conversational edits; asks for the boss's reason, proposes a
  replacement with justification, applies on confirmation. Proposes only — it is
  handed no repository, so it cannot write.
- `app/worker.py` — the durable job loop. PostgreSQL owns the jobs (the
  `copilot_jobs` table, claimed once with `FOR UPDATE SKIP LOCKED`); the
  copilot inbox that named it is gone. The worker runs **inside the API
  process by default** (`PAKASH_EMBEDDED_WORKER=0` turns it off) and can also
  run on its own as `python -m app.worker`. Generation is queued as one job
  per span; manager-chat turns and `compile_sources` are jobs too.
  Several lanes, with at least one reserved for manager chat so a long build
  cannot occupy every worker.
- `bl/schedule_service/` — persistence and ordering around the solver, the
  change agent and the audit: open, build, propose, confirm, apply, publish,
  clear, constraints, history, preferences, simulations, export.
- `bl/audit/` — **pure Python, no LLM.** Recomputes countable facts and returns
  warnings. Never blocks. Also owns `personal_summary()` and `fairness()`, which
  the employee area and the manager's stats read — they live here so one
  person's hours are literally the same arithmetic as the manager's warnings,
  not a second implementation. `shift_stats` counts load in shifts and
  nights as well as hours, takes an `employee` to narrow to one person, and
  is what `schedule_service/statistics.py` runs over any span of dates
  (`window.py` decides which rows and which findings fall inside it).
- `bl/employee_service/` — identity claims, the personal view, constraint
  requests, and the unread-change mark. Approval is the only thing that writes
  a constraint (D14).
- `bl/schedule_service/generation/` — opening a period and running its
  checkpointed job. A job may cover less than its period: `start_generation`
  takes `build_from`/`build_through` (the grid opens whole, the solver is
  asked for the run), and `range.py` opens a job over a run of dates inside
  a draft that already exists — manager-placed rows there are pins, the rest
  of those dates is replaced, every other date is untouched.
  Both also take `shifts` (`shift_filter.py`): only those shift types are
  solved and rewritten, and rows on every other shift stand as fixed rows.
  A range with `keep_existing` holds the rest where it fits instead of
  replacing it (D37), and `absorb.py` opens such a job on every draft ahead
  of today when a profile save adds a soldier or a shift; published weeks
  are listed, never touched.
- `bl/schedule_service.create_blank/assign/unassign` — the manual path (D18).
  Writes with no model and no solver on them.
- `bl/importer/` — a file in, in any shape (D39): one reader for any
  `Layout`, detection scored against the roster, the model asked only to
  describe the layout (never the rows). `schedule_service/importing.py`
  previews (writes nothing) and commits what was approved — a new period, or
  the imported shifts and dates merged into a chosen draft.
- `bl/export.py` — a period out as `.xlsx`. Pure functions, no model, no
  repository. Laid out shift-major like `FILE_FORMATS.md` Sample A.
- `bl/learn/` — what the manager's own corrections say about the workplace.
  `observe_corrections()` counts repeated corrections in the change log (no
  model); `RuleLearner` turns those counts into candidate rules in the
  manager's own words (D2) with the evidence attached. Proposes only — nothing is approved
  by having been proposed.
- `bl/tools/` — **the named questions the agent may ask, answered in pure
  Python.** Eight read-only operations (`read_period`, `team_overview`,
  `employee_state`, `coverage_gaps`, `validate_placement`,
  `find_replacements`, `publish_readiness`, `profile_gaps`); the chat adds
  its own read tools in `chat_tools.py`. No LLM call anywhere in the file, and
  no write: it holds a repository and uses it for reads only (D19).
- `bl/planner/` — what the manager chat shares with the no-model reader:
  the question and tool-call schema, and deterministic answers over
  `bl/tools/` and `bl/intent/`. The model loop that answered `/ask` is gone;
  the manager chat asks instead.
- `bl/intent/` — **reading a Hebrew sentence with no model.** Keyword
  matching against the workspace's own roster and shift vocabulary, seven
  question shapes, and `unknown` for anything else. It never guesses. The
  chat uses it for its zero-model fast path ("who can replace…").
- `bl/absence/` — **an absence, from sentence to plan, with no model** (D36).
  Reads one person and every date ("בשני ושלישי", "מ-1.11 עד 5.11"), asks once
  when dates or scope are missing, ranks clean covers so the load spreads
  evenly, and hands `ChatPlanBuilder.prepare` a model-shaped turn — so the plan
  meets every check a model plan does. Run inline by `start_turn` before the
  model loop (`bl/chat_fast.py`); anything it cannot read goes to the model.
  Also behind the read-only replacement tab, `GET /api/agent/replacements`.
- `bl/simulate/` — what a change *would* do, computed in memory. Handed no
  repository, so persisting nothing is a property of the wiring (D20). The
  chat's `simulate_changes` tool reads it.
- `bl/rotation/`, `bl/placement/` — whose closure a date is, and what a
  placement would cost; pure arithmetic the solver, the board and the audit
  share.
- `bl/prompts/` — prompt text as markdown, loaded by `prompts.load(name)`.
  Shared fragments compose via `<!-- include: shared/name.md -->`.
- `api/` — Pydantic HTTP contracts and routers.
- `main.py` — FastAPI routes, the composition root, and the embedded worker.
- `diagnose.py` — `python -m app.diagnose`: settings, the job queue, model
  slots and a real completion, printed for a terminal on a closed network.

Business logic under `bl/`, data access under `dal/`. A file owns one class or
one concern; split rather than append.

**Size rules.** No file over 300 lines and no function over 50 (docstring
included). A concern that outgrows one file becomes a package: its
`__init__.py` re-exports the public names, so callers keep importing from
the same path, and a facade class (`ScheduleService`, `EmployeeService`,
`ScheduleTools`) composes small collaborators that each own one job. Each
package's `__init__` docstring carries a table of which module owns what.

## Locked rules

- **The audit never blocks.** `bl/audit/` returns warnings and nothing else. It
  does not reject a schedule, rewrite an assignment, or veto the manager.
  The solver is built from the same thresholds so its output is clean by the
  audit's own measure, but the audit itself stays advisory
  ([D3](../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-), D34)
  — a hand-made or edited schedule that breaks a rule still saves.
- **The audit contains no LLM call.** Its entire value is being arithmetic that
  cannot be hallucinated. Pure functions over a roster; trivially unit-testable.
- **Generation honours hard rules; the audit still only warns.** The solver
  will not place a row that breaks a hard rule it can represent (D34). A
  rule it cannot represent is reported in the build's notes, never sent to
  a model to assign around. On a hand-made schedule hard rules remain a
  loud warning, not a gate (D1/D3).
- **How full a slot is has exactly one answer, and `bl/audit/` owns it.**
  `required_headcount()` says how many people it asks for — reading the stored
  grid first, since that is what the week was generated into — and
  `counts_toward_staffing()` says whether the person standing on it fills one
  of those seats. `audit`, `shift_stats`, `tools.coverage_gaps`,
  `simulate._coverage` and the board all go through the pair. A second count
  anywhere is how a coverage bar comes to read 100% directly above a warning
  saying the cell is short, and a manager who has seen that once stops
  believing either number. A shadow shift is where the two counts diverge:
  somebody learning the shift is at work, is on the board, accrues the hours,
  and leaves the slot needing everybody it asked for.
- **Shift names are never hardcoded.** They come from unit setup. Any literal
  `"בוקר"` outside a test fixture or a Hebrew vocabulary table is a bug ([D9](../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
- **No structured rule vocabulary.** Rules are the boss's own sentences ([D2](../docs/DECISIONS.md#d2--rules-stay-natural-language)).
  What code made of one (`compiled_sources`, D32) is a kept derivative,
  looked up by the sentence's words; it never replaces or rewrites it.
- **Every assignment carries the agent's reason**; every change carries the boss's
  reason too. Neither is optional — they serve different purposes ([D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).
  Enforced in three places on purpose: `assignments.reason` is `NOT NULL`, the
  repository refuses a blank one, and the solver writes one on every row it
  places (`bl/solver/solve.py`).
- **A dragged shift is a proposal, not an edit.** `POST /api/schedule/move`
  requires the manager's reason exactly as a spoken change does ([D12](../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).
- **Clearing keeps the grid; deleting does not.** `POST /{id}/clear` empties
  one day's assignments or the period's and leaves the slots standing — the
  week's shape comes from the shift vocabulary (D9), not from what a build
  decided, so a manager taking back a bad build should not have to rebuild
  the week's rows too. `DELETE /{id}` is the other one and removes the
  period outright. Both log every removed row individually: a day cleared in
  one gesture is still N people taken off N shifts, and the change log is
  the only history there is (D4).
- **The rotation is enforced where a shift is assigned, and only ever
  advisory afterwards.** `bl/rotation/` is the single definition of whose
  closure a date is; the solver never creates a variable for a placement
  contradicting it, `placement.py` says so before the click, and `audit.py`
  warns about a schedule that already drifted. Not placing a *generated* row
  is not the audit gaining a veto (D3): it is the same class of bound as "a
  person nobody declared", because the cycle was arithmetic this code
  already did.
- **The boss can build a schedule without the agent** ([D18](../docs/DECISIONS.md#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)).
  `/blank`, `/assign` and `/unassign` call no model at all — `build_slots()`
  was always pure arithmetic. `assign` writes immediately and that is *not* a
  reversal of D12: a drag takes a shift away from somebody, while filling an
  empty cell takes nothing from anybody, so there is no one for a reason to be
  owed to. `assignments.reason` stays `NOT NULL` — a hand-placed row carries
  the manager's sentence or a plain statement that a person placed it.
- **`assignments.source` says where a row came from**, never who typed it —
  `availability.source` (D13) applied to the other table. Defaults to `agent`
  so rows predating the column keep their meaning, and `move_assignment`
  leaves it alone: dragging a hand-placed shift does not make it the agent's.
- **The export layout is Sample A, not a design choice.** `bl/export.py`
  writes the shape the workplace already keeps ([D17](../docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).
- **A message for the team is written by the agent, not templated in code.**
  Posting the week to a group chat is writing, and the manager asks for it in
  the conversation — the manager chat answers with a reply and no operations.
  Nothing is sent anywhere; the product has no channel to the team beyond the
  share link and holds no employee contact details.
- **A learned pattern is not a rule.** `bl/learn/` returns *candidates*
  carrying their evidence, and the leap from a repeated correction to a rule
  is the manager's to make. Anything but an
  explicit `hard` is stored soft — an invented hard rule nags the manager
  about a rule they never stated ([D1](../docs/DECISIONS.md#d1--rules-are-hard-or-soft)).
- **No endpoint lets an employee mutate a schedule.** Enforced by
  `guards.boss()` on every schedule-mutating route — not by convention.
  [D14](../docs/DECISIONS.md) narrowed [D5](../docs/DECISIONS.md#d5--employees-are-read-only)
  but did **not** remove it: a signed-in employee may submit a constraint
  *request* via `guards.employee()` and nothing else. They cannot assign,
  move, publish, or approve — including their own request.
- **A pending constraint request is inert.** It lives in `constraint_requests`,
  not `availability`, so `bl/audit/` cannot see it and submitting one cannot
  move the arithmetic. The manager's approval is what promotes it into an
  `availability` row with `source='employee_reported'` (D13/D14). Keeping the
  two tables separate is what makes that a property of the schema rather than
  a filter every reader must remember.
- **`acknowledged_at` is not `last_seen_at`.** The latter moves on every
  login, so nothing could ever be new against it; the former advances only
  when the employee acknowledges what they were shown, which is what makes
  "what changed for me" answerable ([D16](../docs/DECISIONS.md#d16--an-employee-is-told-what-changed-and-acknowledging-is-what-marks-it-read)).
  A NULL acknowledgement means **everything** is new, not nothing — otherwise
  the first notification, the one that matters most, is swallowed.
- **An acknowledgement gates nothing.** It is not consent and not an
  acceptance; the manager publishes whether or not anyone has read anything.
- **An employee's identity comes off the signed cookie, never the request.**
  `session["employee"]` scopes every personal read. A name accepted from a body
  would let any signed-in employee read a colleague's hours and stated reasons.
- **Every workplace-owned read is scoped by `team_id`, taken from the signed
  session cookie** and never from the request ([D10](../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).
- **Only the operator opens a team** ([D28](../docs/DECISIONS.md)).
  `POST /api/workspace` is 403 unless `PAKASH_OPEN_SIGNUP` is on; the console
  (`/api/admin`, `guards.admin()`) is the door. Its cookie is separate from the
  team cookie and neither reader accepts the other's role.
- **The operator never decides headcount.** Opening a team takes a name and
  a password; the roster, and how many people are on it, is the manager's.
- **`PAKASH_SESSION_SECRET` must be set in any real deployment.** Unset, each
  worker signs with its own key and rejects the others' cookies.
- **A partial profile reports its gaps; it never blocks.** `completeness` is
  read by `profile_gaps`. The solver runs on a thin
  profile and returns a thin schedule — only a profile with no shift
  vocabulary at all is refused, because there is no grid to build (D9).
- **The tool layer never writes** ([D19](../docs/DECISIONS.md#d19--the-agent-answers-with-tools-asking-and-changing-stay-separate)).
  `bl/tools/` is handed a repository and reads from it; the write path
  stays `schedule_service.apply()` behind the manager's confirmation. A tool
  that could write would be a second way to change a schedule, and the
  product deliberately has one.
- **The agent asks rather than guesses what a request refers to.** When
  carrying out a request would mean guessing which person, shift or date it
  means, the agent asks one focused question and proposes nothing. On the
  write path this is enforced **in code**, not by the prompt:
  `changes._proposal` withdraws every operation naming an employee the
  roster cannot resolve — unknown, or shared by several people — exactly as
  it already withdraws one with no reason (D8). The two gates are separate
  and either can hold a proposal, but only one question is asked at a time:
  the target is settled before the reason is collected, because a reason
  recorded against the wrong person is worse than a missing one.
  `tools.resolve_employee` is the single resolver both paths use; it returns
  *several* matches rather than the first, since picking the first is the
  guess the whole gate exists to refuse.
- **Reading may interpret; writing may not.** The chat answers a
  loosely-worded question against a reasonable reading — nothing moves, and a
  re-ask is cheap. A change may not, because a change applied to the wrong
  record has to be found before it can be undone.
- **A clarification continues the request; it does not replace it.**
  `pending_request` travels to the client with the question and back with the
  answer, and the two halves are read as one sentence — the manager answers
  "ערב", never "תשבץ את דניאל במשמרת ערב". It is client-supplied text that
  reaches the model as part of the sentence and nothing else: it names no
  schedule and selects no row, so `team_id` from the signed cookie is still
  the only thing that scopes a write. It is cleared the moment the request is
  carried out, so an answered question cannot be reopened by a stale echo,
  and the agent is shown what it already asked (`asked_last_turn`) so
  the same question is never put twice.
- **A tool failure is not an ambiguous request.** Nothing matching found, a
  technical error, and "which of these did you mean" are three different
  answers. The deterministic fallback answers the question rather than asking
  what the manager meant — an unreachable model is not the manager having
  been unclear, and asking would repeat on every retry.
- **An answer carries no operations.** A manager-chat answer is a reply;
  only a pending plan, applied through its own endpoint, writes. Asking and
  changing stay separate acts.
- **The agent may not claim a placement is valid unless a tool said so.**
  `find_replacements` re-validates every candidate through `bl/placement/`
  and keeps only the clean ones. This is *not* the audit becoming a gate:
  `validate_placement` still returns `blocking: False` and
  `publish_readiness.ready` is descriptive — nothing branches on it before a
  publish (D3).
- **A simulation persists nothing, structurally.** `bl/simulate/` is
  handed no repository at all ([D20](../docs/DECISIONS.md#d20--a-simulation-is-not-a-proposal)),
  like `changes.py`. Approving one is an ordinary
  `apply()` with the manager's reason — there is no dedicated endpoint for
  it, because a second write path is how a confirmation step gets routed
  around.
- **The core works without a model.** Building a schedule from structured
  input calls no model (D34); a build whose sentences could not be
  translated still completes and says what it left out. In the chat, "who
  can replace…" is answered by `bl/intent/` and the tools before any model
  round (`chat_tools.replacement_lookup`). The reader never guesses — an
  agent acting on a misread sentence with no model to blame is worse than
  one that asks.
- **A preference is not a rule and never authorises a write**
  ([D21](../docs/DECISIONS.md#d21--the-agent-remembers-preferences-and-every-one-of-them-is-visible)).
  It reaches the model as reported speech. An agent-proposed one lands
  `suggested` and is inert until the manager approves it, and everything
  stored is listed, editable and deletable.
- **The change log is append-only.** The schedule is edited in place; its history
  lives only in the log ([D4](../docs/DECISIONS.md#d4--living-schedule-not-versioned)).
- Errors leaving the backend are `AgentError` in Hebrew.
- Never log API keys or full prompts containing employee personal details.
  Prompts never leave this process except to the model server.
- Keep the design simple: add a module only when it owns a distinct boundary.
