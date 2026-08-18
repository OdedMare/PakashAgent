# Business logic (`app/bl/`)

Where decisions are made. `bl/` decides *what* to schedule and *how* to interpret
a file; `dal/` only fetches and sends. Nothing here imports `psycopg` or `openai`
directly — it goes through the repository and the LLM client it was constructed
with.

Built so far: `interview.py`, `interview_service.py`, `workspace_service.py`,
`audit.py`, `scheduler.py`, `changes.py`, `briefing.py`, `schedule_service.py`,
`prompts/`. Only `importer.py` remains.

| File | Owns |
|---|---|
| `interview.py` | The intro interview — workplace profile, employees, rules, shift vocabulary |
| `interview_service.py` | Persistence around it: sessions, turns, resume, completion |
| `workspace_service.py` | Workspace rules: entering a team, roles, the share link |
| `scheduler.py` | Generating a schedule; every assignment carries a reason |
| `changes.py` | Conversational edits and the change log |
| `briefing.py` | **The agent speaking first.** Observes; proposes nothing that lands |
| `schedule_service.py` | Persistence and orchestration around all three: propose, confirm, apply |
| `audit.py` | **Pure-Python advisory checks. No LLM.** |
| `importer.py` | Excel/doc ingest with layout inference |
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

Feeds the profile, rules, availability, and recent history to `complete_json`;
gets back assignments **each with its own `reason`**. The reason is not optional
decoration — it is shown to the boss at confirmation time and is the mechanism by
which a bad call gets caught while it's still cheap ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).

Handles both generation and schedules the boss authored or imported — they share
one representation ([D6](../../../docs/DECISIONS.md#d6--the-boss-can-author-or-generate)).

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
- **Every response carrying a schedule carries its warnings**, and a response
  with warnings is still a success.

`propose()` audits the schedule *as the change would leave it*, computed in
memory and never written, so the manager sees the consequence of a change
before accepting it rather than after.

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
- Shift names come from the interview — never hardcoded.
- Rules stay natural language.
- Every assignment carries the agent's reason; every change also carries the
  boss's.
- Imports are confirmed before they persist.
- Business logic stays here; SQL stays in `dal/repository/`; model calls go
  through `dal/llm/`.
