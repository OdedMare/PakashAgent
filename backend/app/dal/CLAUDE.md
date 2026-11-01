# Data access (`app/dal/`)

Fetches and sends. Makes no decisions — those live in `bl/`.

- `database.py` — **pooled** connections; verifies the schema exists
  (never creates it).
- `llm/` — the OpenAI-compatible JSON client. See [llm/CLAUDE.md](llm/CLAUDE.md).
- `repository/` — the only SQL owner in the codebase.
- `notify.py` — `PostgresSignals`: `pg_notify` out, one unpooled `LISTEN`
  connection per process in, on a channel named after the schema (D35).
  The manager's live inbox (`common/events.py`) rides on it.

**PostgreSQL is the only shared state** (D35): data, the job queue
(`jobs.py`, `FOR UPDATE SKIP LOCKED`), the login throttle
(`throttle.py`), live signals (`notify.py`) and the model-call limit
(advisory locks, `llm/model_slots.py`), and what every replica must agree
on — the generated session key and the panel's settings
(`deployment.py`, D39). There is no Redis. `initialize()` creates the
tables under an advisory lock, so replicas starting together do not race.

## Connection pooling

Connections are pooled (`psycopg_pool`, up to `PAKASH_DATABASE_POOL_SIZE` per process, default 16 — enough for six worker lanes beside the API, D38). They were not originally: every query
opened a fresh `psycopg.connect()`, paying a TCP handshake, authentication and
a `SET search_path` round-trip before running any SQL — and one page load
issues several queries. Measured against a local Postgres, that was 1.97ms per
query versus 0.14ms pooled; over a network the gap is wider, because handshake
cost dominates.

Two properties are load-bearing:

- **The pool is re-keyed on the database settings**, the same way `dal/llm/`
  keys its OpenAI client. Without it a database edit saved in the UI would
  appear to do nothing — the pool would keep serving connections to the old
  host forever, which is a far more confusing failure than a slow query. The
  replaced pool is `close()`d rather than dropped, or its sockets leak until
  it happens to be collected.
- **`search_path` is set in `configure`**, which runs once per pooled
  connection rather than once per query. It is connection state, so this is
  both correct and the point of pooling it.

`require_schema()` is deliberately **not** pooled: the pool's `configure` sets
`search_path` to the very schema it is checking for, so borrowing a pooled
connection to ask whether the schema exists would put the question after the
assumption.

**Round trips are the cost to cut, not queries** (D45). Measured with
0.5 ms per network hop, a one-statement read went from 10 ms to 3 ms and
`get_schedule` from 35 ms to 6 ms by removing round trips alone:

- `RepositoryBase._all`/`_execute` borrow through `single_statement()`,
  which runs a pooled connection in **autocommit**: one statement is its own
  transaction anyway, so `BEGIN`/`COMMIT` are not sent. Inside `atomic()`
  or a job's bound connection it lends that connection instead, unchanged.
  A multi-statement write still uses `connect()` and commits itself.
- `pool_hooks.py`: the checkout health check is skipped for a connection
  returned in the last `FRESH_SECONDS`, and the return hook resets
  `autocommit` to off so no later caller inherits it.
- `get_schedule` sends its three queries in one pipeline.
- `team_profile()` sends the document only when `(revision, updated_at)`
  changed since this process last read it (`repository/profile_cache.py`).
  The row is still read every time, so a save from any process is seen at
  once; nothing read inside `atomic()` is cached.

**No PgBouncer in transaction mode.** Session advisory locks (job claim,
model slots), `LISTEN` and the per-connection `search_path` all need a
session (`docs/SCALING.md`).

`close_pool()` runs on FastAPI shutdown. Without it the pool's worker threads
outlive the process and Postgres accumulates idle backends across restarts.

**A pooled connection commits differently.** Leaving a `with connect(...)`
block returns the connection to the pool instead of closing it, and the pool's
context manager commits on a clean exit. Callers that commit explicitly still
should — that is what the repository does, and it stays correct either way.

## Tables

Every table is composed in `schema.py` (DDL in `repository/ddl/`, plus
`chat.py` and `throttle.py`). The workplace, employee roster
and rules remain JSON on the team's profile, which is what
`team_profile()` reads. Manager conversations are separate durable rows: the
parent carries `team_id` and signed browser `manager_id`; messages belong to that
parent. Reads and approvals verify the parent owner before accessing messages.

Chat approval uses `database.py:atomic()` to compose existing repository
writes in one serializable transaction. Their inner `commit()` calls are deferred
until the approval's outer transaction succeeds, so a failed later assignment or
constraint write also rolls back earlier writes and the approval receipt.

**Every workplace-owned table carries `team_id`** ([D10](../../../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).
Add it when the table is created, not later: retrofitting a tenant key onto a
populated table is the expensive version of this, and a table that briefly
exists without one is a table whose reads are briefly unscoped.

`schema.py` commits after each independent block. That is not cosmetic: the
whole script is sent as one simple-query message, which Postgres wraps in a
single implicit transaction, so without the checkpoints one failing guarded
migration rolls back every unrelated statement that already succeeded in the
same call. Add a new guarded migration after its own `COMMIT`.

| Table | Holds |
|---|---|
| `teams` | One workspace: name, the boss's password hash, the member share token — plus the operator's controls (D28): `active` (FALSE = suspended) and `notes` |
| `complexes` | A מכלול (D43): name, the commander's password hash, `active`, `notes`. `teams.complex_id` links a team to at most one; deleting a מכלול leaves its teams standing |
| `complex_duty_types` | A מכלול's duties (מטבח, שמירה…): seats per day, the weekdays it runs, and `weight` — how many shifts a duty day counts as in fairness and statistics |
| `complex_duties` | One soldier (`team_id` + roster name) on one duty for one whole day, owned by the מכלול. Projected into the team's `availability()` as a `duty` with no hours, which blocks midnight to midnight; the team's own constraint delete refuses it |
| `commander_notices` | What a מכלול commander changed inside a team, for that team's own commander: the action in words, a count of folded repeats, `seen_at` |
| `team_profiles` | One structured workplace profile per team, with a `revision` bumped on every save: a save naming an older one is refused (409) instead of silently undoing another manager's edit |
| `schedules` | One living schedule per period, `draft` or `published` |
| `shift_slots` | One shift on one date — the thing an assignment points into |
| `assignments` | person → slot, **with the agent's reason** (`NOT NULL`). `source` records whether the agent generated the row, the manager placed it by hand, or it was imported ([D18](../../../docs/DECISIONS.md#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)) |
| `availability` | Known unavailability. `source` records where it came from — the manager, the agent, or the manager writing down what an employee reported ([D13](../../../docs/DECISIONS.md#d13--constraints-are-recorded-by-the-manager-with-their-source-marked)) |
| `duties` | Blocking operational intervals. Several may exist per person and date; an end not later than the start crosses midnight. Reads are projected into the availability shape so the solver, audit and picker share one overlap calculation |
| `change_log` | **Append-only**: what changed, both reasons, when, and `actor` — who was acting, read from `common/actor.py` (set per request from the signed cookies, and per job from the request that queued it) |
| `employee_identities` | A claimed roster name plus its scrypt passcode hash — one claim per name per team ([D14](../../../docs/DECISIONS.md)). Also holds `acknowledged_at`, the mark behind "what changed for me" ([D16](../../../docs/DECISIONS.md#d16--an-employee-is-told-what-changed-and-acknowledging-is-what-marks-it-read)) |
| `constraint_requests` | An employee's submission awaiting the manager. **Not** `availability`: pending rows are invisible to `bl/audit/`, and approval is what promotes one |
| `compiled_sources` | What code made of a standing sentence (D32), keyed on its words, the roster and the compiler. A derivative of the sentence, never a replacement; `unresolved` rows are kept negatives |
| `source_anchors` | The day each standing sentence was first seen, which relative time ("3 ימים") counts from |
| `swap_requests` | An employee's proposed swap, the colleague's answer, and the manager's ruling |
| `agent_preferences` | What the agent remembers (D21): `suggested`, `active` or `archived`, all visible and editable |
| `manager_chats`, `manager_chat_messages` | One manager's conversations and their turns, with the plan a turn prepared and the receipt of its approval |
| `copilot_jobs` | The durable job queue: chat turns, generation spans, `compile_sources` (named for the copilot that is gone) — claimed once, retried with backoff |
| `login_attempts` | Wrong guesses and lockouts per account (D35). Without `team_id`: the account key already names the team, and the operator and settings accounts belong to none |
| `deployment_state` | Values every process of the deployment shares (D39): the generated session key, the panel's settings. Keyed by name with a `version` to poll; no `team_id`, since it belongs to no team |

The workplace profile — the mission, the **shift vocabulary** (names, times,
on-call flags and weighting), the employees, and the rules — lives as JSON on
`team_profiles.profile` rather than in tables of its own. It is written by unit
setup and read through `team_profile()`. Splitting
it into relational tables would buy nothing today: nothing queries across it, and
the setup form owns its shape.

## Rules

- **Every read of a workplace-owned row filters by `team_id`.** A UUID is hard
  to guess, but "hard to guess" is not an access control — one workspace's boss
  holding another's row id must still get a 404. The team is a required
  argument, not an optional filter.
- **`admin.py` is the one module whose reads cross teams**, for the operator
  console (D28) — and `complexes.py` and `complex_duties.py`, whose commander reads cross only the
  teams of one מכלול, always filtered on `teams.complex_id`. Keep every cross-team query there, name the `teams` columns
  explicitly, and never return a hash.
- **A cross-team miss is a `NotFoundError`, never a distinct "wrong team".**
  Distinguishing them turns any id-taking endpoint into an oracle for which
  rows exist in workspaces the caller cannot see.
- **Passwords are hashed with `scrypt`, never stored or logged in the clear.**
  `teams.password_hash` and `employee_identities.passcode_hash` both end up in
  backups and in psql sessions. Employee passcodes reuse `teams.hash_password`
  rather than a second scheme — one password format, one place to change it.
- **A pending constraint request is never an `availability` row.** Promoting one
  is `bl/`'s job and happens only on the manager's approval; writing it here on
  submission would let an employee move the audit's arithmetic by asking, which
  reverses [D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-️-amended-by-d31-assignment-superseded-by-d34).
- **`change_log` is append-only.** Never update or delete a row. It is the only
  history the system has ([D4](../../../docs/DECISIONS.md#d4--living-schedule-not-versioned)).
- **`acknowledged_at` and `last_seen_at` are different columns on purpose.**
  `last_seen_at` moves on every login, so nothing could ever be new against
  it. `acknowledged_at` moves only when the employee acknowledges what they
  were shown — collapsing the two would silently delete the feature
  ([D16](../../../docs/DECISIONS.md#d16--an-employee-is-told-what-changed-and-acknowledging-is-what-marks-it-read)).
- **`assignments.reason` is not nullable in spirit** — an assignment without the
  agent's reasoning defeats [D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required).
  A hand-placed row is no exception: it carries the manager's own sentence, or a
  plain statement that a person placed it, rather than a blank or a judgment the
  agent never made (D18).
- **`assignments.source` defaults to `agent`.** Every row written before the
  column existed was generated, so the default preserves what those rows already
  meant. `move_assignment` deliberately leaves it alone — dragging a
  hand-placed shift does not make it the agent's.
- A schedule is edited in place. There are no version rows and no rollback.
- Shift names are data, not enums — they come from the profile (`team_profiles.profile`).
- SQL lives here and nowhere else. `bl/` never imports `psycopg`.
- Employee personal details are never written to logs.
