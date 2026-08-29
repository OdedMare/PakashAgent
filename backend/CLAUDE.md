# PakashAgent backend context

Read this before changing `backend/`.

Design decisions with their reasoning: [`../docs/DECISIONS.md`](../docs/DECISIONS.md).
Real Excel layouts: [`../docs/FILE_FORMATS.md`](../docs/FILE_FORMATS.md).

## Purpose

Turn a conversation with the boss into a maintained shift schedule. The agent
learns the workplace once (intro interview), then generates schedules, imports
ones the boss already has, and rearranges them on request — explaining every
decision and recording every reason.

## Runtime and commands

Python is **3.8.10**, mirroring AiSummryIO. Keep annotations compatible: use
`Optional`, `List`, `Dict`; do **not** use `X | Y`, `list[str]`, or `match`.
*(If the deployment target turns out to be newer, this is the one open question
in DECISIONS.md — resolve it before writing much code.)*

```bash
cd backend
python -m pytest -q
uvicorn app.main:app --reload
```

## Architecture

- `common/` — env defaults (`PAKASH_` prefix) plus the live runtime-settings
  override store. Saved settings override env without restart; secrets masked.
- `dal/database/postgres.py` — connection; verifies the schema exists.
- `dal/llm/` — the OpenAI-compatible JSON client and its degradation ladder,
  ported unchanged from AiSummryIO. Model/base URL/API key stay live per call.
- `dal/repository/` — the only SQL owner. `teams.py` also owns password
  hashing (`scrypt`, stdlib) and the member share token.
- `bl/workspace_service.py` — workspace rules: who may enter a team, in which
  role, and what a new workspace inherits.
- `api/dependencies.py` — the route guards (`visitor`, `boss`).
- `common/sessions.py` — signed session cookies (HMAC-SHA256, no library).
- `bl/interview.py` — the intro interview, one `plan-chat` turn at a time
  (ported from AiSummryIO). Collects the workplace profile, employees, rules
  (tagged hard/soft), and the **shift vocabulary**. Every turn returns the
  draft profile so far; `ready` is gated in code, never trusted to the prompt.
  The manager may also **end it early** (`interview_service.end`), which
  writes the partial draft with a `completeness` record of what it still owes
  ([D22](../docs/DECISIONS.md#d22--the-interview-can-be-ended-early-and-the-profile-says-what-it-owes-️-amends-d18)).
- `bl/assignment_agent.py` — **the agent that does the assigning.** Fills one
  date by running the tools below and deciding, weighing the rules the
  manager stated in their own words. Code refuses an unusable row and hands
  the reason back for one corrected turn; a cost the agent accepts, a slot it
  leaves short and a row still refused at the end all come back as **alerts**
  ([D25](../docs/DECISIONS.md#d25--the-agent-assigns-the-tools-count-and-the-engine-is-the-floor-)).
- `bl/assignment_tools.py` — **the questions it may ask about one date,
  answered in pure Python.** No LLM call and no repository: `open_slots`,
  `candidates` (who may take a slot, who may not and why, and what each
  option costs), `check_placement`, `workload`. Both engines take their
  legality, ranking and hour tally from here, so "who may stand on this slot"
  has one answer.
- `bl/deterministic_scheduler.py` — the floor under the agent. Fills a date by
  ranking, with no model at all: it runs when none is configured (the
  deployment default), when the model is unreachable, and when the agent's
  answer cannot be used.
- `bl/scheduler.py` — the slot grid (`build_slots`), the rotation's effective
  availability, and the span planner every build reads. Also the older
  model-driven period scheduler kept for backward-compatible API consumers.
- `bl/changes.py` — conversational edits; asks for the boss's reason, proposes a
  replacement with justification, applies on confirmation. Proposes only — it is
  handed no repository, so it cannot write.
- `bl/briefing.py` — **the agent speaking first.** Reads the current state and
  says what it noticed, unprompted. Returns exactly `headline`, `items`,
  `quiet` — no operations, so there is no path from a briefing to a write.
- `bl/copilot.py` + `app/worker.py` — the durable observation loop. PostgreSQL
  owns jobs, inbox items, per-action permissions and append-only audit events;
  the separate worker survives browser and API restarts.
- `bl/schedule_service.py` — persistence and ordering around those three plus
  the audit: propose, confirm, apply, publish, constraints, history.
- `bl/audit.py` — **pure Python, no LLM.** Recomputes countable facts and returns
  warnings. Never blocks. Also owns `personal_summary()` and `fairness()`, which
  the employee area renders — they live here so one person's hours are literally
  the same arithmetic as the manager's warnings, not a second implementation.
- `bl/employee_service.py` — identity claims, the personal view, constraint
  requests, and the unread-change mark. Approval is the only thing that writes
  a constraint (D14).
- `bl/schedule_service.create_blank/assign/unassign` — the manual path (D18).
  The only schedule writes with no model call anywhere on them.
- `bl/export.py` — a period out as `.xlsx`. Pure functions, no model, no
  repository. Laid out shift-major like `FILE_FORMATS.md` Sample A so an
  exported week can be edited and imported back.
- `bl/importer.py` — Excel/Word ingest with layout inference. **No model
  call**: which axis is time and whether shift is nested under date is grid
  arithmetic, and code that counts cannot hallucinate a person into a shift.
  Three layouts, scored against each other: `shift_major` (Sample A),
  `person_major` (Sample B), and `date_only` — dates and people with no shift
  axis at all, tried last and only when no row carries a lane label, so a real
  shift axis is never flattened into it. Column headers written as hours
  (`07:00-15:00`) fold into the declared shift running those hours rather than
  becoming a second shift with the same meaning. Returns an `Interpretation`;
  handed no repository, so it cannot write.
- `bl/learn.py` — what a stack of past files says about the workplace.
  `observe()` counts patterns across every uploaded file (no model);
  `RuleLearner` turns those counts into candidate rules in the manager's own
  words (D2) with the evidence attached. Proposes only — nothing is approved
  by having been proposed.
- `bl/tools.py` — **the named questions the agent may ask, answered in pure
  Python.** Seven read-only operations (`read_period`, `employee_state`,
  `coverage_gaps`, `validate_placement`, `find_replacements`,
  `publish_readiness`, `profile_gaps`). No LLM call anywhere in the file, and
  no write: it holds a repository and uses it for reads only (D19).
- `bl/planner.py` — the loop that runs them. The model picks tools, the
  tools answer with arithmetic, the results go back. Falls back to
  `bl/intent.py` when no model is reachable, so the same questions are
  answered with nothing configured.
- `bl/intent.py` — **reading a Hebrew sentence with no model.** Keyword
  matching against the workspace's own roster and shift vocabulary, six
  question shapes, and `unknown` for anything else. It never guesses.
- `bl/simulate.py` — what a change *would* do, computed in memory. Handed no
  repository, so persisting nothing is a property of the wiring (D20).
- `bl/prompts/` — prompt text as markdown, loaded by `prompts.load(name)`.
  Shared fragments compose via `<!-- include: shared/name.md -->`.
- `api/` — Pydantic HTTP contracts and routers.
- `main.py` — FastAPI routes and composition root.

Business logic under `bl/`, data access under `dal/`. A file owns one class or
one concern; split rather than append.

## Locked rules

- **The audit never blocks.** `bl/audit.py` returns warnings and nothing else. It
  does not reject a schedule, rewrite an assignment, or veto the agent. Making it
  authoritative reverses [D3](../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)
  — the whole product shape depends on the agent keeping the judgment.
- **The audit contains no LLM call.** Its entire value is being arithmetic that
  cannot be hallucinated. Pure functions over a roster; trivially unit-testable.
- **Hard rules are not gates.** They are strong instructions to the model plus a
  loud warning when broken. This is a deliberate, accepted tradeoff — see D1/D3.
- **The agent assigns; code refuses only what cannot stand**
  ([D25](../docs/DECISIONS.md#d25--the-agent-assigns-the-tools-count-and-the-engine-is-the-floor-)).
  An unusable row — a person or shift nobody declared, somebody unqualified,
  a hard constraint, another group's closure, one person twice, no reason —
  is refused and the reason is handed *back to the agent*, which is the same
  bound `scheduler.py` always applied. A merely expensive row is the agent's
  to take: a sixth consecutive day, hours past the ceiling, a short rest, a
  soft preference overridden. Widening the refusals to those is the audit
  becoming a gate through a side door.
- **Every trade the agent makes is loud.** Each accepted cost becomes an
  alert carrying the agent's own reason whether or not the agent mentioned
  it, and so does every slot left short. An alert is not a warning: `audit.py`
  recomputes what is true of the stored schedule, an alert records what
  happened while it was being built. They ride along on the schedule, reach
  the copilot inbox, and are handed to the briefing — and none of them gates
  a publish.
- **A build always produces a schedule.** `_assign_day` is the one seam every
  build goes through, and an `AgentError` out of the agent runs
  `deterministic_scheduler.generate_day` instead. No model is configured in
  the default deployment, so the fallback is a supported path rather than an
  error path; `metrics.engine` says which side built the day.
- **How full a slot is has exactly one answer, and `bl/audit.py` owns it.**
  `required_headcount()` says how many people it asks for — reading the stored
  grid first, since that is what the week was generated or imported into — and
  `counts_toward_staffing()` says whether the person standing on it fills one
  of those seats. `audit`, `shift_stats`, `tools.coverage_gaps`,
  `simulate._coverage` and the board all go through the pair. A second count
  anywhere is how a coverage bar comes to read 100% directly above a warning
  saying the cell is short, and a manager who has seen that once stops
  believing either number. A shadow shift is where the two counts diverge:
  somebody learning the shift is at work, is on the board, accrues the hours,
  and leaves the slot needing everybody it asked for.
- **Shift names are never hardcoded.** They come from the interview. Any literal
  `"בוקר"` outside a test fixture or a Hebrew vocabulary table is a bug ([D9](../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
  On import this means *matched against* the declared vocabulary, not
  *restricted to* it: a header that matches none is taken from the sheet's own
  wording, because the file records something the workplace really ran and
  dropping it would silently lose history. Nothing is invented — a name is
  either the workplace's or the manager's file's. A sheet naming no shift at
  all (`date_only`) imports with the name **empty**, and the confirm screen
  asks; filling it in with a guess is the bug D9 is about.
- **No structured rule vocabulary.** Rules are the boss's own sentences ([D2](../docs/DECISIONS.md#d2--rules-stay-natural-language)).
- **Every assignment carries the agent's reason**; every change carries the boss's
  reason too. Neither is optional — they serve different purposes ([D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).
  Enforced in three places on purpose: `assignments.reason` is `NOT NULL`, the
  repository refuses a blank one, and `scheduler.py` drops an unreasoned row
  rather than storing it.
- **A briefing observes; it never acts.** `bl/briefing.py` returns three keys
  and none of them is an operation, so nothing it says can be applied
  ([D15](../docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).
  A `suggestion` is a sentence the manager may send, after which the ordinary
  propose-then-confirm path runs unchanged. Giving a briefing operations that
  `apply` could read would reverse D3, D8 and D12 at once.
- **A briefing never counts.** `warnings` and `fairness` are computed by
  `audit.py` and handed to the model as facts. Speaking first does not move
  the D3 line about which side does arithmetic.
- **`schedule_service.brief()` never raises.** It returns quiet on any failure:
  it decorates a screen that must render regardless of what the model is doing.
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
  advisory afterwards.** `bl/rotation.py` is the single definition of whose
  closure a date is; `scheduler.py` refuses to store a row contradicting it,
  `placement.py` says so before the click, and `audit.py` warns about a
  schedule that already drifted. Refusing a *generated* row is not the audit
  gaining a veto (D3): it is the same class of bound as "a person nobody
  declared", because the cycle was arithmetic this code already did.
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
  writes the shape `bl/importer.py` is being built to read, so a week can
  leave and come back ([D17](../docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).
  Changing the layout to something prettier produces a file this product
  cannot read.
- **A message for the team is written by the agent, not templated in code.**
  Posting the week to a group chat is writing, and the manager asks for it in
  the conversation — the change agent answers with `reply` and no operations.
  Nothing is sent anywhere; the product has no channel to the team beyond the
  share link and holds no employee contact details.
- **An import is never committed before confirmation.** Inference produces an
  interpretation the boss approves; only then does anything persist ([D7](../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)).
  Split across two endpoints so the confirmation is structural rather than a
  dialog in front of a write that already happened: `/import/preview` reads
  and returns, `/import/confirm` is the only one that writes. `confirm` takes
  the rows back from the caller rather than re-reading the file, so a name the
  manager corrected on the screen is what gets stored.
- **An imported schedule keeps the shifts it actually ran.** `commit_import`
  builds the slot grid from the file's own rows, not from `build_slots` —
  regenerating it from today's vocabulary would quietly reshape history to
  match a profile that may have changed since ([D9](../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
- **A learned pattern is not a rule.** `bl/learn.py` returns *candidates*
  carrying their evidence, and the leap from "has not happened" to "must not
  happen" is the manager's to make: a file showing nobody on Saturday may mean
  Saturday is closed, or that the sheet only covered weekdays. Anything but an
  explicit `hard` is stored soft — an invented hard rule nags the manager
  about a rule they never stated ([D1](../docs/DECISIONS.md#d1--rules-are-hard-or-soft)).
- **No endpoint lets an employee mutate a schedule.** Enforced by
  `guards.boss()` on every schedule-mutating route — not by convention.
  [D14](../docs/DECISIONS.md) narrowed [D5](../docs/DECISIONS.md#d5--employees-are-read-only)
  but did **not** remove it: a signed-in employee may submit a constraint
  *request* via `guards.employee()` and nothing else. They cannot assign,
  move, publish, or approve — including their own request.
- **A pending constraint request is inert.** It lives in `constraint_requests`,
  not `availability`, so `bl/audit.py` cannot see it and submitting one cannot
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
- **`PAKASH_SESSION_SECRET` must be set in any real deployment.** Unset, each
  worker signs with its own key and rejects the others' cookies.
- **The interview has two doors, and only a person opens the second one.**
  `_is_ready` governs what the *model* may declare finished and still refuses
  a profile owing a required field; `interview_service.end` is the manager's
  own act and calls no model at all (D22). An agent able to reach `end` would
  be deciding it had asked enough — the judgement the confirmation turn keeps
  with the manager.
- **A partial profile reports its gaps; it never blocks.** `completeness` is
  read by `profile_gaps` and rendered on the board. The scheduler runs on a
  thin profile and returns a thin schedule — refusing would be the audit
  becoming a gate through a side door (D3/D22).
- **The tool layer never writes** ([D19](../docs/DECISIONS.md#d19--the-agent-answers-with-tools-asking-and-changing-stay-separate)).
  `bl/tools.py` is handed a repository and reads from it; the write path
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
- **Reading may interpret; writing may not.** `bl/planner.py` answers a
  loosely-worded question against a reasonable reading — nothing moves, and a
  re-ask is cheap. `bl/changes.py` may not, because a change applied to the
  wrong record has to be found before it can be undone.
- **A clarification continues the request; it does not replace it.**
  `pending_request` travels to the client with the question and back with the
  answer, and the two halves are read as one sentence — the manager answers
  "ערב", never "תשבץ את דניאל במשמרת ערב". It is client-supplied text that
  reaches the model as part of the sentence and nothing else: it names no
  schedule and selects no row, so `team_id` from the signed cookie is still
  the only thing that scopes a write. It is cleared the moment the request is
  carried out, so an answered question cannot be reopened by a stale echo,
  and both agents are shown what they already asked (`asked_last_turn`) so
  the same question is never put twice.
- **A tool failure is not an ambiguous request.** Nothing matching found, a
  technical error, and "which of these did you mean" are three different
  answers. The deterministic fallback answers the question rather than asking
  what the manager meant — an unreachable model is not the manager having
  been unclear, and asking would repeat on every retry.
- **An answer carries no operations.** `POST /api/schedule/ask` returns
  `answer`, `steps`, `needs_confirmation` — and nothing `apply` could read,
  the same guard `bl/briefing.py` has (D15). Asking and changing are
  separate acts, separate endpoints, and separate cards on the screen.
- **The agent may not claim a placement is valid unless a tool said so.**
  `find_replacements` re-validates every candidate through `bl/placement.py`
  and keeps only the clean ones. This is *not* the audit becoming a gate:
  `validate_placement` still returns `blocking: False` and
  `publish_readiness.ready` is descriptive — nothing branches on it before a
  publish (D3).
- **A simulation persists nothing, structurally.** `bl/simulate.py` is
  handed no repository at all ([D20](../docs/DECISIONS.md#d20--a-simulation-is-not-a-proposal)),
  like `changes.py` and `importer.py`. Approving one is an ordinary
  `apply()` with the manager's reason — there is no dedicated endpoint for
  it, because a second write path is how a confirmation step gets routed
  around.
- **The product answers without a model.** `bl/planner.py` falls back to
  `bl/intent.py` over the same tools and reports `used_model: false`. The
  fallback covers six question shapes and says plainly when it did not
  understand — it never guesses, because an agent acting on a misread
  sentence with no model to blame is worse than one that asks.
- **A preference is not a rule and never authorises a write**
  ([D21](../docs/DECISIONS.md#d21--the-agent-remembers-preferences-and-every-one-of-them-is-visible)).
  It reaches the model as reported speech. An agent-proposed one lands
  `suggested` and is inert until the manager approves it, and everything
  stored is listed, editable and deletable.
- **The change log is append-only.** The schedule is edited in place; its history
  lives only in the log ([D4](../docs/DECISIONS.md#d4--living-schedule-not-versioned)).
- Errors leaving the backend are `AgentError` in Hebrew.
- Never log API keys or full prompts containing employee personal details.
- Keep the design simple: add a module only when it owns a distinct boundary.
