# Business logic (`app/bl/`)

Where decisions are made. `bl/` decides *what* to schedule and *how* to interpret
a file; `dal/` only fetches and sends. Nothing here imports `psycopg` or `openai`
directly — it goes through the repository and the LLM client it was constructed
with.

Built so far: `interview.py`, `interview_service.py`, `workspace_service.py`,
`audit.py`, `scheduler.py`, `changes.py`, `briefing.py`, `export.py`,
`schedule_service.py`, `prompts/`. Only `importer.py` remains.

| File | Owns |
|---|---|
| `interview.py` | The intro interview — workplace profile, employees, rules, shift vocabulary |
| `interview_service.py` | Persistence around it: sessions, turns, resume, completion |
| `workspace_service.py` | Workspace rules: entering a team, roles, the share link |
| `scheduler.py` | Checkpointed range generation, one date or one week per call; every assignment carries a reason |
| `changes.py` | Conversational edits and the change log |
| `briefing.py` | **The agent speaking first.** Observes; proposes nothing that lands |
| `schedule_service.py` | Persistence and orchestration around all three: propose, confirm, apply |
| `audit.py` | **Pure-Python advisory checks. No LLM.** Also the fairness arithmetic the scheduler and the employee area read |
| `export.py` | **A period out as `.xlsx`.** Pure functions, no model, no repository |
| `importer.py` | Excel/doc ingest with layout inference |
| `tools.py` | **The named questions the agent may ask. Pure Python, no LLM, no write** — including `profile_gaps`, what the interview never taught |
| `planner.py` | The tool loop, with a deterministic fallback when no model is reachable |
| `intent.py` | **Reading a Hebrew sentence with no model.** Seven shapes; never guesses |
| `simulate.py` | **What a change would do.** No model, no repository, persists nothing |
| `rotation.py` | **Whose closure a date is.** Pure arithmetic off separate round/triplet anchors; no model |
| `placement.py` | **What a placement would cost, and what else the manager could do.** No model |
| `prompts/` | Prompt text as markdown, `prompts.load(name)`, with `<!-- include: -->` composition |

## The division that defines this layer

The agent decides. Code audits. ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-))

Everything except `audit.py` is model-driven and returns natural language the boss
reads. `audit.py` is the opposite: no model, no prose, just arithmetic over a
roster returning a list of warnings. That split is deliberate and load-bearing —
an LLM asked "has anyone exceeded 5 shifts?" is doing arithmetic by generation,
and a wrong answer looks identical to a right one.

## `interview.py`

The turn shape is ported from the `plan-chat` planners in AiSummryIO
(`bl/workflow_engine_pkg/conversational_planning.py`). One question per turn,
each carrying the agent's own `recommendation`, a `why`, and two to four
clickable `options`. An option's `answer` is a full sentence sent verbatim as
the boss's own message — never a label, never an index, because a bare number
may be either a selection or a real value and the interview must clarify
rather than guess. Below two options the list is dropped: one option is not a
choice.

**Options are asked for on every question, including open-ended ones.** The
free-text composer sits beside the buttons and never goes away, so offering a
concrete sentence to correct costs the boss nothing and beats handing them an
empty field. `_options` is the bound, not the policy — the policy is in
`prompts/shared/interview_method.md`.

**The model is shown what it already asked.** `recent_conversation` carries
the recent stretch of the thread and `questions_already_asked` carries every
question put so far, including ones scrolled out of that window. Neither the
draft nor `resolved` records *questions* — only settled facts — so a model
given the last exchange alone cannot tell a fresh topic from one it just
covered, and re-asks until the interview circles instead of ending.

**`resolved` and `open_points` are deduplicated, not concatenated.** Both are
replayed to the model as `*_so_far` every turn and come back carried forward,
and `open_points` then has `missing_topics()` appended to it in code. A blind
`+` therefore stacked the code-generated sentence beside the model's echo of
that same sentence, once per turn, for as long as the gap stayed open — so
"נשאר לסגור" grew a longer and longer list of one line. `_unique` preserves
the agent's own ordering rather than sorting: the panel is read top to bottom.

**A `reply` that promises an update it did not make is caught in code.**
`reply` is prose the manager reads; `draft_update` is what is stored. A model
answering "אני מעדכן את המדיניות" with an empty update has silently dropped
what the manager just said. `_promised_unkept` requires *both* halves — an
empty update alone is ordinary, since a clarifying question settles nothing —
and records the loss as an open point so it is visible instead of vanishing.
Compared against the merged draft, so re-sending a field's existing value
counts as recording nothing too.

Every turn also returns `draft` — the profile so far — plus `resolved` and
`open_points`, the agent's own account of what is settled and what is not. The
draft is **merged** across turns (`_merged_draft`): the model rebuilds it from
scratch each turn, so a narrow answer that re-emits only the field it touched
would otherwise blank the twenty it did not, precisely at the confirmation
turn. A field is carried forward only when the new turn left it empty, so a
correction still lands.

**The interview never acts on its own conclusion.** `_is_ready` is the gate,
enforced in code rather than trusted to the prompt: a turn that still asks
something, or that is only now presenting its summary for approval
(`awaiting_confirmation`), is never `ready` however the model labelled itself.
A draft still missing a required topic is not ready either — the gap resurfaces
in `open_points` instead of the boss discovering it after the session closed.
`ready` is what closes the session and writes the profile.

**There is a second door, and only the manager opens it.** `end()` closes the
interview with whatever has been collected, records what it still owes on the
profile as `completeness`, and **calls no model**
([D22](../../../docs/DECISIONS.md#d22--the-interview-can-be-ended-early-and-the-profile-says-what-it-owes-️-amends-d18)).
The gate above is unchanged — it governs what the *model* may declare
finished. Keeping them separate is the decision: an agent that could reach
`end` would be deciding it had asked enough. `missing_topics()` is public so
both doors and `tools.profile_gaps` share one definition of "missing".

Collects:
- the workplace profile (what the job is, the mission) — free text
- the employees
- **the shift vocabulary** — the workplace's own shift names, their times, and
  **whether any are on-call**. On-call (`כונן לילה` in one real file) may count
  differently toward hours and fairness; ask, because `audit.py` needs the weight.
- dependencies between workers
- rules, each tagged **hard** or **soft** as it is stated

Rules are stored as **the boss's own sentences** ([D2](../../../docs/DECISIONS.md#d2--rules-stay-natural-language)).
Do not parse them into typed records — that was considered and rejected.

The declared shift vocabulary is what `importer.py` matches sheet headers against,
so this must run before a meaningful import.

The completed product mock and the prompt lessons it exposed are documented in
[`../../../docs/INTERVIEW_REFERENCE.md`](../../../docs/INTERVIEW_REFERENCE.md).

`IntroInterview` is **stateless on purpose** — it is a function of the
conversation plus the draft it is handed, which is what lets its whole
contract be tested against a fake model with no database.
`interview_service.py` is the piece that owns remembering: it appends each
turn, stores the pending turn so a refresh resumes without a model call, and
writes the profile once `ready` turns true. Keep that split. Folding
persistence into `IntroInterview` would cost the tests that make its gating
trustworthy.

The reference is stateless on *both* sides — its client replays the history
and the draft on every turn. Here the session holds them instead, so a boss
who refreshes or opens the app on a second machine resumes the profile they
had rather than the empty one their browser happened to keep. The draft handed
to the model is read back from the session, never taken from the request, so a
stale client copy cannot rewrite what was already agreed.

## `scheduler.py`

Feeds the profile, rules, availability, and the **fairness tally** to
`complete_json`; gets back assignments **each with its own `reason`**. The reason is not optional
decoration — it is shown to the boss at confirmation time and is the mechanism by
which a bad call gets caught while it's still cheap ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).

Handles both generation and schedules the boss authored or imported — they share
one representation ([D6](../../../docs/DECISIONS.md#d6--the-boss-can-author-or-generate)).

**Past assignments are counted, not sent.** The scheduler used to hand the
model several hundred raw history rows and let it work out who had been taking
the nights. That was wrong twice: on a two-week period those rows were roughly
60% of the entire prompt — crowding out the period actually being built, on
models whose context is the binding constraint — and counting them is code's
job under [D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-).
`audit.load_history()` now does the arithmetic and the model receives the
tally: ~9,100 tokens of rows become ~470 of counts.

This is the same move `briefing.py` already makes with `warnings` and
`fairness`. Reducing the prompt is the side benefit; the reason it belongs on
this side of the line is that a model asked "who worked the most nights" is
doing arithmetic by generation, and a wrong answer looks exactly like a right
one.

**How wide one call is, is a setting.** `schedule_generation_mode` chooses
between `day` — one date per model call, the default — and `week`, which asks
for up to seven in one. Both run the *same* pipeline (`generate_span`): the
same candidate lists, the same response schema, the same rejection rules, the
same audit. Nothing is trusted in `week` that `day` would not trust. What
changes is the granularity of the repair (a bad row re-answers the whole span)
and the cost of a failure. `plan_spans` divides the period, and a week is a
ceiling rather than a promise — a span never crosses seven days nor carries
more staffing demand than one answer can hold.

**A repair call is only ever asked for what a repair could fix.** The audit
finding that carries no date — `over_hours`, a weekly total — is reported
beside the schedule but excluded from `_span_warnings`, because the repair
instruction forbids touching earlier dates and the hours came from there.
Before that distinction, one person crossing their ceiling on a Wednesday
bought a second model call on every remaining day of the week, none of which
could clear it.

**The roster is sent once per call, not twice.** `candidate_employees` is the
authoritative list — filtered to who is legally available, keyed by the ids
the schema accepts — so `_profile_beside_candidates` drops `employees` from
the profile beside it. A blacklist of one key, never a whitelist: a field list
here is how newly collected interview facts silently stop travelling.

**Interactive generation is one checkpoint per request.**
`ScheduleService.start_generation()` stores the whole slot grid, plans the
spans for the configured mode, and writes a JSON checkpoint on the draft;
`/generate/{id}/next` calls `generate_span()` once. The browser repeats that
request for a single date or an arbitrary range. A failed span is marked
`failed` and the same endpoint retries it, so completed neighbours survive a
timeout or refresh.

Progress is counted in **dates**, never in checkpoints: `total_days` and
`completed_days` measure the period, so a week-wide build fills the manager's
bar day by day rather than jumping by seven.

**A transient failure costs a pause, not the period.** `generate_next` still
checkpoints a failed span and raises — one step is one step, and `/next`
answers its caller with the error. The *durable loop* is what decides to try
again: `_requeue_failed_span` puts a span with attempts left back in the queue
and backs off, up to `_MAX_SPAN_ATTEMPTS`. Nobody is watching a background
build, so a job that parked itself on the first blip waited for a person who
might not return for an hour. Bounded, because the failures that are not
transient repeat identically.

**A checkpoint writes only its own dates.** `replace_span_assignments` deletes
by date rather than rebuilding the period, which was quadratic (a thirty-day
build re-inserted every earlier day thirty times) and lossy: each rewrite
minted fresh ids, so an `assignment_id` the browser was holding pointed at
nothing by the time it was used.

**A running job says so, and can be stopped.** `/generate/{id}/run` launches
a worker and returns; `GET /{id}/progress` is what the browser polls, and it
carries the counter alone rather than the period and a fresh audit over it.
Two fields make that poll terminate:

- `heartbeat`, stamped every `GENERATION_HEARTBEAT_SECONDS` by the worker and
  at every checkpoint. `llm_timeout_seconds` defaults to no limit, so a model
  that is slow to answer and one that has hung look identical from outside —
  both are `running` forever. A beat that stops is the difference, and it
  means the job has lost its worker (a restarted process, a killed thread).
  `POST /run` adopts such a job and resumes it from the first unfinished day.
- `cancel_requested`, set by `/generate/{id}/cancel`. Cooperative rather than
  forceful: a model call in flight cannot be interrupted, so the worker stops
  at the next day boundary and every finished day is kept. The period is an
  ordinary draft immediately, and `/run` resumes it later.

**The board stays writable while a job runs**, which is what makes the two
above matter rather than being merely tidy. A shift the manager places by
hand on a date that has not been generated yet becomes a pin: it goes into
the day's `required_assignments`, and `_persisted_generation_rows` keeps it
with the manager's own source whether or not the model repeats it.

Each daily payload carries legal candidate ids, the previous day's concrete
assignments, and a fairness tally over the earlier range. Code audits the
answer and may make one focused repair call. It never loops indefinitely; an
unresolved problem remains an ordinary schedule warning.

The original `generate()` chunked-period method remains for backward-compatible
API consumers. The management UI uses only the checkpointed daily flow.

Three properties make the split safe, and each has a test:

- **A day is never divided across two calls.** `_chunks` splits on dates, not
  on slot count. Half a Tuesday in one request and half in another is how one
  person ends up on two shifts at once, with neither call able to notice.
- **Later chunks see earlier ones.** Each is passed `already_scheduled`, and
  its `fairness` tally is recomputed over the real history *plus* what this
  run has already placed. A scheduler blind to week one hands week two to the
  same people — turning the fairness feature into the unfairness it exists to
  prevent.
- **A date is exactly one primary call.** It gets at most one additional call
  when deterministic validation supplies a concrete repair request.

Assignments are bounded against the whole grid rather than the current chunk,
so a model naming a date from next week is not penalised for answering early.
On a duplicate the earlier chunk wins: the later call is the one working from
incomplete information, and it was told what was already scheduled.

The audit still sees the merged period, never the chunks — a run of
consecutive shifts crossing a boundary is caught exactly as one inside a week
is.

## `changes.py`

The step-4 loop: *"Dana's sick Thursday."*

1. Parse the request.
2. **If the boss gave no reason, ask for one.** Required ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).
3. Propose a replacement **with the agent's justification**.
4. On confirmation: apply to the living schedule, append to the change log.

The schedule is edited in place; the change log is append-only and is the only
history ([D4](../../../docs/DECISIONS.md#d4--living-schedule-not-versioned)).
No versioning, no rollback.

**Two gates, both enforced in code, and either can hold a proposal.**
`needs_reason` is the missing *why* (D8). `needs_input` is the missing
*what* — a change whose target could not be resolved without guessing.
`_unresolved_people` checks every name an operation carries against
`tools.resolve_employee`, and a name that matches nobody, or several people,
empties the proposal and turns it into a question. Neither gate is left to
the prompt: a model that forgets `needs_reason` once writes an unexplained
row into the only history there is, and one that forgets `needs_input` once
moves the wrong person's shift — which has to be *found* before it can be
undone. Only one question is asked per turn, target before reason, because a
manager handed two questions answers neither.

**A dropped operation is never silent.** `_operations` bounds what the model
proposes to targets that exist, and it used to do that by discarding the rest
without a word: the model answered *"העברתי את דנה"*, code found no slot for
the row it named, and the manager was left with a confident sentence, no
confirm button, and a schedule that had not moved — the agent appearing to
ignore them. It now returns what it dropped alongside what it kept, and the
proposal either asks (several possible shifts — the same question shape as an
unresolvable name) or reports which target was not there. It also reads an
empty `shift` as **the whole day**, the convention `schedule_service._match`
has always used: *"תוריד את דנה מיום חמישי"* names a person and a date, and
bounding it against the slot grid threw it away every time, because `("",
date)` is not a slot.

**What can be done is still proposed.** A request whose fourth operation has
no target still carries the other three; holding all of them behind one
question would make every multi-step change all-or-nothing.

`pending_request` is how the answer resumes the request rather than replacing
it. Plain text, joined with the manager's reply and sent as one sentence —
deliberately not a parsed pending-intent record, since the sentence is what
the model already reads and a structured duplicate is a second thing to keep
in sync. Cleared as soon as the request is carried out.

## `rotation.py` — whose weekend it is

A closure (`סגירה`) is not another shift to balance. It is a stretch one
group holds, and balancing it away — handing Saturday to whoever is under
quota — breaks the cycle the unit planned its month around. So the cycle is
**computed, not asked of the model**, for the same reason `audit.py` is code:
"which group closes on the weekend of 12/09" is arithmetic, and a wrong
answer to it looks exactly like a right one (D3).

**A closure weekend is Thursday to Sunday morning.** Four dates, not one
Saturday: the group goes in on Thursday (on `shushim`, Friday), holds Friday
and Saturday, and is relieved at the Sunday handover. Every pattern ends at
the same handover and they differ only in when the stretch begins. The Sunday
tail covers **the day's first shift by the clock** — found by reading the
declared start times, never by matching a Hebrew morning name, because shift
vocabulary is per workplace (D9). A workplace whose shifts carry no times has
no clock to read, so its closures honestly end on Saturday rather than
blocking a Sunday on a guess.

**Each cycle is anchored, not inferred.** Round and triplet may use separate
anchor dates and first groups. Legacy profiles fall back to
`first_closure_*`; with no anchor for a pattern every function returns nothing
rather than guess a phase that puts the wrong group in.

Read by four callers, which is the point of it being one module:
`scheduler.py` turns it into hard availability rows and refuses assignments
that contradict them, `audit.py` warns about a schedule that already drifted
(`cross_rotation`), `placement.py` tells the board whose closure a slot is
before the manager clicks, and `changes.py` hands the same schedule to the
model so a spoken change sees the rotation too.

## `briefing.py` — the agent speaking first

The only model call in this package that answers nothing the manager said. It
reads the current state and says what it noticed
([D15](../../../docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).

Four triggers, each changing what is worth saying: `opened`, `changed`,
`publishing`, `periodic`.

**It returns exactly three keys — `headline`, `items`, `quiet`.** That is the
guard, not a coincidence: there is no field a confirmation could read, so
there is no path from a briefing to `apply`. An item's `suggestion` is a
sentence the manager may *send*; the ordinary propose-then-confirm loop then
runs unchanged. An agent that acted on its own conclusion would reverse D3,
D8 and D12 together — being proactive here means *initiating the
conversation*, never skipping it.

**The model is never asked to count.** `warnings` and `fairness` arrive
already computed by `audit.py` and are handed over as facts to reason about.
Speaking first does not move the D3 line about which side does arithmetic.

`quiet` is decided in code from whether there are items, not taken from the
model's own label — the two disagreeing would render an all-clear above a
list of problems. Silence is the common case by design: an agent that finds
something urgent every time gets tuned out, which is the only way this
feature actually fails.

`schedule_service.brief()` swallows failures and returns quiet. This sits
beside a calendar that must render regardless of what the model is doing.

## `tools.py`, `planner.py`, `intent.py` — answering a question

The multi-step half of the agent
([D19](../../../docs/DECISIONS.md#d19--the-agent-answers-with-tools-asking-and-changing-stay-separate)).
`ChangeAgent` puts the whole period in front of the model and asks for
operations, which works for one absence and stops working for *"מי יכול
להחליף את יוסי בסופ״ש"* — four countable things resolved in order, which is
what D3 already assigns to code.

So the questions are **named**, and each is answered by arithmetic:
`team_overview`, `read_period`, `employee_state`, `coverage_gaps`, `validate_placement`,
`find_replacements`, `publish_readiness`, `profile_gaps`. The model picks
which to call and writes the Hebrew around the result; it never supplies a number, a name or a
verdict.

**Nothing in this path writes.** `tools.py` holds a repository and reads from
it. `planner.py` holds the *tools*, not the repository. The response schema
has no operation in it, so there is nothing `apply` could consume — the same
guard `briefing.py` has.

**The agent may not claim a placement is valid unless a tool said so.**
`find_replacements` re-validates every candidate through `placement.py` and
keeps only the clean ones. That is a constraint on *assertion*, not a veto:
`validate_placement` still returns `blocking: False`, and the manager may
still place somebody it warns about (D3).

`intent.py` is the floor. With no model configured — the deployment default
here — it reads the sentence by matching against the workspace's own roster
and shift vocabulary, runs the same tools, and renders Hebrew templates.
Anything it cannot place comes back `unknown` with a list of what it *can*
answer. **It never guesses**: an agent acting on a misread sentence with no
model to blame is worse than one that asks.

**Reading may interpret where writing may not.** A question answered against
a reasonable reading of a loose sentence costs a re-ask and moves nothing, so
the planner asks only when a guess would change *what it reports*. The bar is
not "is a field missing" but "would guessing change the answer". A failed
tool is never a clarification: `found: false` is a complete answer, an error
is an error, and only *several matches* is a question for the manager.

## `simulate.py` — what a change would do

Answers *"מה יקרה אם…"* with an impact report: warnings introduced and
resolved, coverage before and after, hours per affected person, and everyone
touched — including the person a change takes a shift *away* from
([D20](../../../docs/DECISIONS.md#d20--a-simulation-is-not-a-proposal)).

Handed **no repository**, so persisting nothing is structural rather than a
rule to remember — the same shape `changes.py` and `importer.py` have. The
warning diff keys on code/person/date/shift rather than on the message,
because `_over_hours` writes its running total into the sentence and a
warning that merely got worse would otherwise read as a new one.

Deliberately not `propose()`: a proposal is an answer with a confirm button,
and a manager thinking out loud has not asked for one. Approving a simulation
is an ordinary `apply()` with their reason — there is no dedicated endpoint,
because a second write path is how a confirmation step gets routed around.

## `audit.py` — the advisory checker

**Pure functions. No LLM call. Never blocks.**

Recomputes the countable facts and returns warnings:

- hours per person, this week and this month
- consecutive shifts / insufficient rest between them
- double-booking (one person, two places, one slot)
- assignments that contradict a known unavailability
- unfilled slots

Returns a list of warnings. It does **not** mutate a schedule, reject one, or
override the agent. If you find yourself giving it veto power, re-read
[D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-) — the
boss chose this shape knowingly, including its tradeoff with D1.

On-call shifts may weight differently — read the weighting from the interview's
shift vocabulary rather than assuming.

`fairness()` and `load_history()` answer two different questions from the same
arithmetic. `fairness()` compares hours inside the period on screen;
`load_history()` looks *backwards* across past periods at who has carried the
nights and the weekends, and is what `scheduler.py` reasons from when deciding
whose turn the next one is. Both keep people with nothing on the roster — a
zero is the most useful row in either table, and an absent row reads as missing
data. Neither decides anything.

**A night comes off the shift's own flag** (`is_night` / `is_on_call`), never
from its name or its start time. The vocabulary is per-workplace
([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)), so
matching against a list of names nobody declared is exactly the hardcoding that
decision forbids. A workplace that flags no nights honestly reports zero.

**Pass `slots` when you have them.** `audit()` takes the schedule's slot grid as
well as the assignments. A slot with nobody on it leaves no row among the
assignments, so an audit walking only those reports nothing for an entirely
unstaffed shift — the case the manager most needs told about. The assignments
are the fallback for callers that have no stored grid.

**A seat has one definition, and it lives here.** How many people a slot asks
for (`required_headcount`) and whether the person on it fills one
(`counts_toward_staffing`) are public for the same reason `personal_summary`
sits beside `_shift_hours`: four readers need those two answers — the unfilled
warning, the coverage chart, `tools.coverage_gaps` and `simulate._coverage` —
and a fifth spelling of either is how the bar ends up reading 100% above a
warning that says the cell is short. Both are pure arithmetic, and both are
imported rather than restated:

- **The stored grid outranks the profile.** `build_slots` already worked the
  headcount out per date, the board measures cells against it, and an imported
  week's grid records what the *file* ran with (D9). Recomputing from today's
  profile instead is how a Friday generated to ten seats gets graded against
  the four the rest of the week uses. Callers holding a schedule must therefore
  carry `headcount` on the slots they project — dropping it silently reinstates
  the profile fallback.
- **A shadow shift is somebody at work who is not a seat.** Someone learning
  the shift appears on the board and accrues the hours, and the slot still needs
  the people it asked for. Counting bodies reports it covered by the one person
  there because they cannot yet cover it.

This file is the easiest thing here to get exactly right and the easiest to test.
Build it early and table-drive its tests.

## `schedule_service.py`

Owns what `scheduler.py`, `changes.py` and `audit.py` deliberately do not: the
repository, and the order things happen in.

Two shapes are load-bearing:

- **Propose and apply are separate calls.** A proposal writes nothing; the
  manager confirms in between ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).
  A drag on the calendar goes through the same two steps as a typed sentence —
  the gesture is a proposal, not an edit ([D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).
- **The manual path is the exception, and deliberately so.** `create_blank`,
  `assign` and `unassign` write immediately and call no model
  ([D18](../../../docs/DECISIONS.md#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)).
  They are the authoring half of D6, which until now had no implementation.
  Filling an empty cell takes nothing away from anybody, so nothing is owed a
  justification; `assignments.reason` is still never blank.
- **Every response carrying a schedule carries its warnings**, and a response
  with warnings is still a success.

`propose()` audits the schedule *as the change would leave it*, computed in
memory and never written, so the manager sees the consequence of a change
before accepting it rather than after.

## `export.py`

A period out as `.xlsx`, shift-major with dates across the top — the shape of
Sample A in [`../../../docs/FILE_FORMATS.md`](../../../docs/FILE_FORMATS.md).
That layout is the point, not a style: it is what `importer.py` is being
built to read, so an exported week can be edited in Excel and brought back
([D17](../../../docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).

The grid is built from the **slot grid** and then filled from the
assignments, never from the assignments alone — an unstaffed shift leaves no
assignment row, which is the same trap `audit.py` documents for the unfilled
warning. An empty cell means the shift does not run that day; `UNFILLED`
means it runs and nobody is on it. Conflating them would report a gap that
does not exist.

**A message for the team is not here.** That is the agent's job, answered in
`changes.py` as `reply` with no operations.

## `importer.py`

Excel/doc ingest. Full format evidence: [`../../../docs/FILE_FORMATS.md`](../../../docs/FILE_FORMATS.md).

`openpyxl`/`pandas` read the raw grid including merged header cells. The model then
infers **axis semantics** — which axis is time, whether shift is nested under date,
whether the other lanes are shifts or people. The two real samples differ on every
one of those, so none may be assumed.

Each cell is classified: name → assignment, `לא זמין`/`לא זמינה` → unavailability,
empty → nothing. **Availability and assignments share one grid.**

Shift headers match against the interview's vocabulary ([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
Hebrew weekdays and both date formats (`d/M/yy`, `d.M`) parse via a shared
vocabulary module.

Emits an interpretation for the boss to confirm. **Nothing persists before
confirmation** ([D7](../../../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)).

## Rules

- `audit.py` warns; it never blocks, rewrites, or vetoes.
- `audit.py` contains no LLM call, ever.
- `tools.py`, `intent.py` and `simulate.py` contain no LLM call, ever.
- Nothing on the answering or simulating path writes. `tools.py` reads;
  `planner.py` and `simulate.py` are handed no repository to write with.
- An answer carries no operations, and a simulation is approved through the
  ordinary `apply()` with the manager's reason — never through a shortcut.
- Shift names come from the interview — never hardcoded.
- Rules stay natural language.
- Every assignment carries the agent's reason; every change also carries the
  boss's.
- Imports are confirmed before they persist.
- Business logic stays here; SQL stays in `dal/repository/`; model calls go
  through `dal/llm/`.
