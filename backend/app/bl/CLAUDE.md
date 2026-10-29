# Business logic (`app/bl/`)

Where decisions are made. `bl/` decides *what* to schedule and *how* to interpret
a file; `dal/` only fetches and sends. Nothing here imports `psycopg` or `openai`
directly — it goes through the repository and the LLM client it was constructed
with.

A concern that outgrew one file is a package (see the size rules in
[`../../CLAUDE.md`](../../CLAUDE.md)); each package's `__init__` docstring
tables which module owns what. `importer/` reads the workplace's own files in any shape (D42).

| File | Owns |
|---|---|
| `profile_service/` | Structured workplace profile validation and updates |
| `workspace_service.py` | Workspace rules: entering a team, roles, the share link |
| `admin_service.py` | **The צוות משמרות זהב console** (D28): operator sign-in, opening, re-capping, suspending and deleting teams |
| `scheduler/` | Building a span: the grid, translating the manager's words, then the solver |
| `solver/` | **The OR-Tools CP-SAT constraint solver that assigns every schedule** (D34), and holds the existing board when a change is absorbed (D37). No model |
| `changes/` | Conversational edits and the change log |
| `manager_chat.py`, `chat_*.py` | **The agent**: one saved conversation per manager, plans prepared per turn and applied only on approval (see below) |
| `employee_service/` | Identity claims, the personal view, constraint requests, swaps, the unread-change mark |
| `learn/` | Candidate rules from the manager's repeated corrections. Proposes only |
| `schedule_service/` | Persistence and orchestration around all three: propose, confirm, apply |
| `audit/` | **Pure-Python advisory checks. No LLM.** Also the fairness arithmetic the stats and the employee area read |
| `export.py` | **A period out as `.xlsx`.** Pure functions, no model, no repository |
| `importer/` | **A file in, in any shape** (D42). The shape is a `Layout`; detection reads it every plausible way and scores against the roster; the model only describes the layout when unsure, never the rows. No repository, no write |
| `tools/` | **The named questions the agent may ask. Pure Python, no LLM, no write** — including `profile_gaps`, what setup still lacks, and the range questions (`who_works`, `workload_ranking`, `who_is_away`, `shadow_partners`) |
| `planner/` | The chat's question/tool-call schema and the deterministic no-model answers |
| `intent/` | **Reading a Hebrew sentence with no model.** Seven shapes; never guesses |
| `absence/` | **An absence read and planned in code** (D36): dates, one question when needed, the fairest cover per shift; no model, no write |
| `simulate/` | **What a change would do.** No model, no repository, persists nothing |
| `rotation/` | **Whose closure a date is, and who is home on a day cycle.** Pure arithmetic off separate anchors; no model |
| `placement/` | **What a placement would cost, and what else the manager could do.** No model |
| `prompts/` | Prompt text as markdown, `prompts.load(name)`, with `<!-- include: -->` composition |
| `shared.py` | Small helpers several packages read: text and date coercion, Hebrew weekdays, `role_qualified`/`allowed_roles`, `resume` (a clarification joined to its request) |
| `directive_agent/` | **Translating the manager's words for the solver.** A bounded tool loop; code validates the answer, keeps every source that translated whole, reports the rest, and writes nothing |
| `compiled_sources/` | **Standing sentences translated once and kept** (D32): keys, time anchoring, the cache port, the worker's compiler. No model, no SQL |
| `schedule_requests.py` | **Structured scheduling requests** (`avoid`, `prefer`, `max_count`, `not_together`, `min_rest`, `max_consecutive`, `balance`, `requires_with`) and their one validator |

## The division that defines this layer

The solver assigns; the model talks; code audits. ([D34](../../../docs/DECISIONS.md),
amending [D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-))

Who works which shift is solved by `solver/`, an optimisation over the
roster, never generated. The model translates the manager's sentences into
structured requests, holds the conversation, and proposes changes the
manager confirms. `audit/` stays what it was: no model, no prose, just
arithmetic over a roster returning a list of warnings. That split is
load-bearing — an LLM asked "has anyone exceeded 5 shifts?" is doing
arithmetic by generation, and a wrong answer looks identical to a right one.

## `scheduler/` and `solver/` — building a span (D34)

**Two steps, and only the first may call a model.** `Scheduler.generate_span`
collects every sentence code cannot read on its own (`directives.
semantic_sources`: the build's instruction, rules, policies, employee notes,
preferences) and hands them to the `DirectiveAgent`, which answers with
validated absences, pins and structured requests. The solver then assigns
every slot of the span in one solve. Structured input costs no model call.

**A sentence that did not translate is reported, never routed around.**
There is no AI scheduler to fall back to. A binding source left out becomes
a note — "הנחיה מחייבת לא נאכפה בשיבוץ" — and a wish "בקשה רכה לא נלקחה
בחשבון בשיבוץ"; an unreachable model leaves every source out the same way,
and the build still completes.

**The solver (`bl/solver/`)** is OR-Tools CP-SAT:

- `problem.py` decides legality before any variable exists: eligibility,
  the shift's `allowed_roles` (empty restricts nobody; otherwise only a
  person holding one of them is a candidate, `shared.role_qualified`),
  hard availability (dated, recurring, inactive), rotation presence and
  closure — including an ungrouped חמשושים/שושים person, who is home every
  weekend from Thursday (Friday on שושים) to the Sunday handover — and a
  hard `avoid`. Pins are checked and refused with a Hebrew error
  when they break one of those. Fixed rows — pins, the draft outside the
  span, the last 14 days — take part in every count.
- `rules.py` states the audit's blocking checks as constraints, from the
  same `policy()` thresholds: seats (never over headcount), rest between
  shifts, runs of consecutive days, weekly hours. A right-hand side made
  negative by fixed rows is clamped at zero, so placing nobody is always
  feasible and the solver never answers "no schedule".
  **נחפפים** (`service_type` overlap, not counted toward staffing) get
  variables too but take no seat: each stands only beside one of their
  trainers (their own `trainers`, else whoever `can_train`, else any
  counted member), never more of them than counted people on the shift,
  and is rewarded up to a regular share or the training policy's
  `shadow_shifts_per_week`. Rest, runs of days and weekly hours apply to
  them; their row's reason names whom they shadow.
- `requests.py` turns each structured request into a constraint (hard) or
  a priced term (soft), and prices soft availability.
- `fairness.py` rewards closers on their own closure, spreads shifts (not
  hours: on base nobody is on the clock) and nights towards a target per
  person — the demand poured evenly, but never below what someone already
  carries nor above what they can take (`water_fill`), so a part-timer is
  not counted at a share they cannot reach — and prices every pair of one
  person's shifts by the square of the hours their gap falls short of 48
  (`SPACING_HOURS`), so the longest and most even rest wins (back-to-back days are charged instead only when
  shifts carry no clock). Each target is a constant computed before solving
  (a target that moved with the answer made optimality unprovable). Both
  the distance from the target and the largest overload are priced, per
  unit of load and independent of team size: one shift of evenness is
  cheaper than a soft wish (`model.py`) and dearer than any one gap.
- `solve.py` solves in two phases: coverage (unfilled seats, missing roles,
  the shift manager) first — started from the kept board when a rebuild
  keeps one (D37) — then, with coverage fixed as a ceiling and the first
  answer as a hint, everything else. It writes a reason on every row,
  turns every priced term the answer still pays for into a note, and audits
  the result.

**Spans are up to four weeks** (`slots.plan_spans`). A longer period is
solved in such blocks, each seeing the rows of the ones before it as fixed.
Progress is still counted in dates.

**A rebuild can keep what it had** (D37). `keep=` rewards each existing
row for staying put (`solver/stability.py`), priced at half of what moving it
from an overloaded person to an underloaded one gains in evenness — so a new
soldier takes shifts only from whoever is above their share, and a new shift
is filled around the rows already there. A range job with `keep_existing`
does this per span and first adds the shift's slots to the stored grid;
`schedule_service/generation/absorb.py` opens one on every draft ahead of
today when a profile save adds a person or a shift. A draft with nothing on
it is not solved, but a new shift still gets its empty rows there.

**A build can be narrowed to some shift types** (`generation/shift_filter.py`):
only the chosen shifts are solved and rewritten, and rows on every other
shift stand as fixed rows that still count for rest and load.

**Interactive generation is a durable job.** `start_generation` stores the
grid and the spans; the worker solves one span per job, checkpoints it, and
retries a failed span a bounded number of times. `cancel` stops at the next
span boundary and keeps every finished one; a hand-placed row on a date not
yet solved is a pin. `POST /generate` solves a whole period inside the
request for callers that want the schedule back rather than a job.

## `manager_chat.py` and `chat_*.py` — the agent

The one place the manager talks to the agent; see
[`docs/MANAGER_CHAT.md`](../../../docs/MANAGER_CHAT.md). A turn runs as a
`manager_chat` job: `chat_reply.py` first tries the zero-model fast path
(`chat_tools.team_question` for who works / who did the most / who is away
when no one is named and the time is, and `chat_tools.replacement_lookup`,
over `intent/` and `tools/`), then up to
seven model rounds that may call read-only tools, then `chat_planner.py`
validates and audits the plan the model proposes — changes (a seat a
removal leaves empty is filled by the solver over the touched dates (D40),
`chat_vacancies.py`: the other rows are pins, whoever left is a hard
`avoid`, and only picks on vacated slots join the plan; `leave_vacant`
keeps a seat empty on request; a model-picked cover for a seat the same
plan vacates is dropped so the solver fills it), a generation
preview (the solver, through `chat_generation.py`), a vocabulary rebuild
(`chat_lifecycle.py`, keeping existing rows where they fit), profile or
constraint edits (`chat_constraints.py`: up to 126 per plan; a refusal names
the row, the offending value and the valid names or shifts so the model can
repair that one row; whole-day words read as an empty shift, "8" as 08:00,
an exact repeated row once; a row naming a `role` instead of an employee is one
row per holder), management actions. A profile patch names only the employees
or shifts it adds or changes; the rest stay as they are. Before the model loop,
`bl/absence/` answers an absence in code (D36): a bare "עד X" runs from the
earliest other day named, or today; spans up to 120 days; shifts in several
stored periods plan the earliest and list the rest. Nothing is written until the manager
approves; `chat_apply.py` then applies the stored plan in one transaction,
after checking the state it was prepared against has not moved. `chat_state.py` gathers
what a turn starts from — its payload is serialised slowest-changing first
(profile, schedule … conversation, request) so the server's prefix cache
survives a new turn, and the schedule in it is written out for the model as
`schedule_for_chat` (per date and shift: seats and names, no reasons); `chat_draft.py` saves the reply as it streams.

## `changes/`

The step-4 loop: *"Dana's sick Thursday."* `changes/proposal.py` is what
the manager chat builds every change plan with; `ChangeAgent` (`/propose`)
is the older one-shot caller of the same gates.

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
`questions.unresolved_people` checks every name an operation carries against
`tools.resolve_employee`, and a name that matches nobody, or several people,
empties the proposal and turns it into a question. Neither gate is left to
the prompt: a model that forgets `needs_reason` once writes an unexplained
row into the only history there is, and one that forgets `needs_input` once
moves the wrong person's shift — which has to be *found* before it can be
undone. Only one question is asked per turn, target before reason, because a
manager handed two questions answers neither.

**A dropped operation is never silent.** `targets.bound_operations` bounds what the model
proposes to targets that exist, and it used to do that by discarding the rest
without a word: the model answered *"העברתי את דנה"*, code found no slot for
the row it named, and the manager was left with a confident sentence, no
confirm button, and a schedule that had not moved — the agent appearing to
ignore them. It now returns what it dropped alongside what it kept, and the
proposal either asks (several possible shifts — the same question shape as an
unresolvable name) or reports which target was not there. It also reads an
empty `shift` as **the whole day**, the convention `schedule_service/operations.match`
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

## `rotation/` — whose weekend it is

A closure (`סגירה`) is not another shift to balance. It is a stretch one
group holds, and balancing it away — handing Saturday to whoever is under
quota — breaks the cycle the unit planned its month around. So the cycle is
**computed, not asked of the model**, for the same reason `audit/` is code:
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

**Each cycle is anchored, not inferred.** Round, triplet and רבעון (`quad`:
א–ד, one weekend in four) may use separate anchor dates and first groups. Legacy profiles fall back to
`first_closure_*`; with no anchor for a pattern every function returns nothing
rather than guess a phase that puts the wrong group in.

**A cycle is stated once, for its first group, and the rest is derived.** The
anchor is one weekend and one group; every other group's turn follows from
it. Closure hours work the same way: `closures.configured_window` reads the
rows `rotation_closure_windows` carries for group א and applies them to
whichever group owns the weekend, so the manager types one definition per
cycle. A row naming another group is that group's own exception and wins for
it — the shape setup uses when group ב leaves at a different
hour. `rotation_presence` is deliberately **not** derived: "ב is out on
Tuesdays" says nothing about א.

**A weekly pattern needs no group.** A חמשושים or שושים person with no
`rotation_group` goes home every weekend, so `presence.closure_status`
refuses their Thursday (Friday on שושים)–Sunday-handover slots outright;
the audit warns about one already placed there.

**Day cycles are the other kind** (`rotation/day_cycles.py`): 11/3, 12/2,
שבוע־שבוע — N days on base, M home, from one anchor day, with each group
starting a stated number of days after it (spread evenly by default). They
live in `workplace.day_cycles`, several side by side, and a person joins one
with `exit_pattern = "cycle:<id>"`. Their weekends fall out of the arithmetic
rather than anchoring it. Hours come in three layers that each state only
what they change — the cycle's own departure and return (a day shift of up
to three days either way, plus a time), `group_times[group]`, then dated
`time_changes` matched on the nominal departure day. A home stretch is hard
unavailability (`closure_status` returns it), so the solver, the audit and
the picker all read it through the same gate as a closure.

Read by four callers, which is the point of it being one module:
`scheduler/` turns it into hard availability rows and the solver never
places a row that contradicts them, `audit/` warns about a schedule that
already drifted (`cross_rotation`), `placement/` tells the board whose
closure a slot is before the manager clicks, and the chat hands the same
closures to the model so a spoken change sees the rotation too.

## `tools/`, `planner/`, `intent/` — answering a question

How the chat answers
([D19](../../../docs/DECISIONS.md#d19--the-agent-answers-with-tools-asking-and-changing-stay-separate)).
*"מי יכול להחליף את יוסי בסופ״ש"* is four countable things resolved in
order, which is code's job, not the model's.

So the questions are **named**, and each is answered by arithmetic:
`team_overview`, `read_period`, `employee_state`, `coverage_gaps`, `validate_placement`,
`find_replacements`, `publish_readiness`, `profile_gaps`. The model picks
which to call and writes the Hebrew around the result; it never supplies a number, a name or a
verdict.

**Nothing in this path writes.** `tools/` holds a repository and reads from
it. The chat's answers carry no operation; only a pending plan, applied
through its own endpoint, writes.

**The agent may not claim a placement is valid unless a tool said so.**
`find_replacements` re-validates every candidate through `placement/` and
keeps only the clean ones. That is a constraint on *assertion*, not a veto:
`validate_placement` still returns `blocking: False`, and the manager may
still place somebody it warns about (D3).

`intent/` is the floor. It reads the sentence by matching against the
workspace's own roster and shift vocabulary; the chat's fast path runs it
before any model round and, for a replacement question it recognises,
answers from the same tools with `planner/fallback_answers.py` and spends
no tokens. Anything it cannot place comes back `unknown` and goes to the
model. **It never guesses**: an agent acting on a misread sentence with no
model to blame is worse than one that asks.

**Reading may interpret where writing may not.** A question answered against
a reasonable reading of a loose sentence costs a re-ask and moves nothing, so
the chat asks only when a guess would change *what it reports*. The bar is
not "is a field missing" but "would guessing change the answer". A failed
tool is never a clarification: `found: false` is a complete answer, an error
is an error, and only *several matches* is a question for the manager.

## `simulate/` — what a change would do

Answers *"מה יקרה אם…"* with an impact report: warnings introduced and
resolved, coverage before and after, hours per affected person, and everyone
touched — including the person a change takes a shift *away* from
([D20](../../../docs/DECISIONS.md#d20--a-simulation-is-not-a-proposal)).

Handed **no repository**, so persisting nothing is structural rather than a
rule to remember — the same shape `changes/` has. The
warning diff keys on code/person/date/shift rather than on the message,
because `_over_hours` writes its running total into the sentence and a
warning that merely got worse would otherwise read as a new one.

The chat's `simulate_changes` tool reads it through
`ScheduleService.simulate`. Deliberately not a plan: a manager thinking out
loud has not asked for a confirm button. Acting on a simulation is an
ordinary plan the manager approves — there is no dedicated write path,
because a second one is how a confirmation step gets routed around.

## `audit/` — the advisory checker

**Pure functions. No LLM call. Never blocks.**

Recomputes the countable facts and returns warnings:

- hours per person, this week and this month
- consecutive shifts / insufficient rest between them
- double-booking (one person, two places, one slot)
- assignments that contradict a known unavailability
- unfilled and overstaffed slots, a missing role or shift commander
- a placement against the rotation (`cross_rotation`)

The codes live in `audit/codes.py`; each check is a module under
`audit/checks/`.

Returns a list of warnings. It does **not** mutate a schedule, reject one, or
override the manager. The solver is built from the same thresholds
(`roster.policy()`; a profile that states no policy gets a base's week —
eleven consecutive days, eight hours' rest, and a weekly hours ceiling of the
whole week, so hours bind nothing until the manager sets a limit and load is
evened in shifts), so a solved schedule is clean by this measure; a
hand-edited one may not be, and that is the manager's call. If you find
yourself giving the audit veto power, re-read
[D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-) and D34.

On-call shifts may weight differently — read the weighting from the profile's
shift vocabulary rather than assuming.

`fairness()` and `load_history()` answer two different questions from the same
arithmetic. `fairness()` compares hours inside the period on screen;
`load_history()` looks *backwards* across past periods at who has carried the
nights and the weekends. (The solver does its own counting over the fixed
rows it is handed, the last two weeks included.) Both keep people with nothing on the roster — a
zero is the most useful row in either table, and an absent row reads as missing
data. Neither decides anything.

**Night counts use `audit.roster.is_night`.** Declared nights/overnight/on-call
shifts count, as do shifts crossing midnight or starting from 22:00 through
05:59. Effective slot hours take precedence over vocabulary hours. Names are
never matched: the editor records times without requiring a night flag. The
solver spreads nights with the same `is_night`, beside an even count of shifts.

**Pass `slots` when you have them.** `audit()` takes the schedule's slot grid as
well as the assignments. A slot with nobody on it leaves no row among the
assignments, so an audit walking only those reports nothing for an entirely
unstaffed shift — the case the manager most needs told about. The assignments
are the fallback for callers that have no stored grid.

**A seat has one definition, and it lives here.** How many people a slot asks
for (`required_headcount`) and whether the person on it fills one
(`counts_toward_staffing`) are public for the same reason `personal_summary`
sits beside `roster.shift_hours`: four readers need those two answers — the unfilled
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

## `schedule_service/`

Owns what `scheduler/`, `solver/`, `changes/` and `audit/` deliberately do
not: the repository, and the order things happen in — opening periods,
generation jobs, the manual path, propose/apply, publish, constraints,
preferences, statistics and the export.

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
It is the layout the workplace already keeps
([D17](../../../docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).

The grid is built from the **slot grid** and then filled from the
assignments, never from the assignments alone — an unstaffed shift leaves no
assignment row, which is the same trap `audit/` documents for the unfilled
warning. An empty cell means the shift does not run that day; `UNFILLED`
means it runs and nobody is on it. Conflating them would report a gap that
does not exist.

**A message for the team is not here.** That is the agent's job, answered in
the manager chat as a reply with no operations.

## `importer/` — reading the workplace's own files (D42)

A sheet's shape is data: `Layout` names which way time runs, the header
line, an optional nested shift line, what a lane is, and the sheet's own
markers. `reader.py` reads any sheet against any layout; `detect.py` tries
every plausible one and scores each by how many cells resolve to roster
people on declared shifts; `mapper.py` asks the model (flow `import`) for a
layout only when detection is unsure or the manager described the file —
the model sees the sheet's corner and returns a layout, **never rows**, and
its layout must out-score detection's to be used. `roster.py` matches names
without guessing. Nothing here writes: `schedule_service/importing.py`
stores what the manager confirmed.

## Rules

- `audit/` warns; it never blocks, rewrites, or vetoes.
- `audit/` contains no LLM call, ever.
- `tools/`, `intent/`, `absence/` and `simulate/` contain no LLM call, ever.
- Nothing on the answering or simulating path writes. `tools/` reads;
  `planner/` and `simulate/` are handed no repository to write with.
- `solver/` contains no LLM call, and the model never assigns anybody (D34).
- An answer carries no operations, and a simulation is approved through the
  ordinary `apply()` with the manager's reason — never through a shortcut.
- Shift names come from unit setup — never hardcoded.
- Rules stay natural language.
- Every assignment carries the agent's reason; every change also carries the
  boss's.
- Business logic stays here; SQL stays in `dal/repository/`; model calls go
  through `dal/llm/`.
