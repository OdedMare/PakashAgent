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
| `scheduler.py` | Generating a schedule; every assignment carries a reason |
| `changes.py` | Conversational edits and the change log |
| `briefing.py` | **The agent speaking first.** Observes; proposes nothing that lands |
| `schedule_service.py` | Persistence and orchestration around all three: propose, confirm, apply |
| `audit.py` | **Pure-Python advisory checks. No LLM.** Also the fairness arithmetic the scheduler and the employee area read |
| `export.py` | **A period out as `.xlsx`.** Pure functions, no model, no repository |
| `importer.py` | Excel/doc ingest with layout inference |
| `tools.py` | **The named questions the agent may ask. Pure Python, no LLM, no write** |
| `planner.py` | The tool loop, with a deterministic fallback when no model is reachable |
| `intent.py` | **Reading a Hebrew sentence with no model.** Six shapes; never guesses |
| `simulate.py` | **What a change would do.** No model, no repository, persists nothing |
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
each carrying the agent's own `recommendation`, a `why`, and up to four
clickable `options`. An option's `answer` is a full sentence sent verbatim as
the boss's own message — never a label, never an index, because a bare number
may be either a selection or a real value and the interview must clarify
rather than guess. Below two options the list is dropped: one option is not a
choice.

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

**A long period is built one week at a time.** Past `_CHUNK_DAYS` (7), the
slot grid is split and the model is asked once per week. The binding
constraint is the *output*, not the context: a fortnight of three daily
shifts is ~126 assignments each carrying its own Hebrew sentence, and a small
model asked for all of them in one reply loses consistency somewhere in the
middle. It is an attention limit, not a context one.

Three properties make the split safe, and each has a test:

- **A day is never divided across two calls.** `_chunks` splits on dates, not
  on slot count. Half a Tuesday in one request and half in another is how one
  person ends up on two shifts at once, with neither call able to notice.
- **Later chunks see earlier ones.** Each is passed `already_scheduled`, and
  its `fairness` tally is recomputed over the real history *plus* what this
  run has already placed. A scheduler blind to week one hands week two to the
  same people — turning the fairness feature into the unfairness it exists to
  prevent.
- **A short period is still exactly one call.** The common case does not pay
  for the long one.

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
`read_period`, `employee_state`, `coverage_gaps`, `validate_placement`,
`find_replacements`, `publish_readiness`, `profile_gaps`. The model picks which to call and
writes the Hebrew around the result; it never supplies a number, a name or a
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
