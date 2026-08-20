# Data access (`app/dal/`)

Fetches and sends. Makes no decisions — those live in `bl/`.

- `database/postgres.py` — **pooled** connections; verifies the schema exists
  (never creates it).
- `llm/` — the OpenAI-compatible JSON client. See [llm/CLAUDE.md](llm/CLAUDE.md).
- `repository/` — the only SQL owner in the codebase.

## Connection pooling

Connections are pooled (`psycopg_pool`). They were not originally: every query
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

`close_pool()` runs on FastAPI shutdown. Without it the pool's worker threads
outlive the process and Postgres accumulates idle backends across restarts.

**A pooled connection commits differently.** Leaving a `with connect(...)`
block returns the connection to the pool instead of closing it, and the pool's
context manager commits on a clean exit. Callers that commit explicitly still
should — that is what the repository does, and it stays correct either way.

## Tables

Built so far: `teams`, `interview_sessions`, `interview_turns`, `schedules`,
`shift_slots`, `assignments`, `availability`, and `change_log` (all in
`schema.py`). `workplace_profile`, `employees`, `rules` and `conversations` are
not separate tables: the interview's confirmed profile holds all four as JSON on
`interview_sessions.profile`, which is what `team_profile()` reads.

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
| `teams` | One workspace: name, the boss's password hash, the member share token |
| `interview_sessions` | One intro interview: its **team**, status, the confirmed profile, the pending question. `reopen()` puts a completed one back in progress **keeping its profile** ([D19](../../../docs/DECISIONS.md#d19--the-interview-can-be-ended-early-and-reopened-later--amends-d9)) |
| `interview_turns` | Each turn; assistant turns keep the options they offered as `payload` |
| `schedules` | One living schedule per period, `draft` or `published` |
| `shift_slots` | One shift on one date — the thing an assignment points into |
| `assignments` | person → slot, **with the agent's reason** (`NOT NULL`). `source` records whether the agent generated the row, the manager placed it by hand, or it was imported ([D18](../../../docs/DECISIONS.md#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)) |
| `availability` | Known unavailability. `source` records where it came from — the manager, the agent, or the manager writing down what an employee reported ([D13](../../../docs/DECISIONS.md#d13--constraints-are-recorded-by-the-manager-with-their-source-marked)) |
| `change_log` | **Append-only**: what changed, both reasons, when |
| `employee_identities` | A claimed roster name plus its scrypt passcode hash — one claim per name per team ([D14](../../../docs/DECISIONS.md)). Also holds `acknowledged_at`, the mark behind "what changed for me" ([D16](../../../docs/DECISIONS.md#d16--an-employee-is-told-what-changed-and-acknowledging-is-what-marks-it-read)) |
| `constraint_requests` | An employee's submission awaiting the manager. **Not** `availability`: pending rows are invisible to `audit.py`, and approval is what promotes one |

The workplace profile — the mission, the **shift vocabulary** (names, times,
on-call flags and weighting), the employees, and the rules — lives as JSON on
`interview_sessions.profile` rather than in tables of its own. It is written
once when the interview is confirmed and read through `team_profile()`. Splitting
it into relational tables would buy nothing today: nothing queries across it, and
the interview owns its shape.

## Rules

- **Every read of a workplace-owned row filters by `team_id`.** A UUID is hard
  to guess, but "hard to guess" is not an access control — one workspace's boss
  holding another's session id must still get a 404. `InterviewRepository` is
  the worked example: the team is a required argument, not an optional filter.
- **`team_profile()` filters on the profile existing, not on the session
  being closed.** A session reopened to add more keeps the profile it was
  completed with, and the management area must go on scheduling against that
  version while the boss answers ([D19](../../../docs/DECISIONS.md#d19--the-interview-can-be-ended-early-and-reopened-later--amends-d9)).
  Re-adding `status='complete'` here makes adding one fact to a workplace an
  outage for as long as the interview is open.
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
  reverses [D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-).
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
- Shift names are data, not enums — they come from `workplace_profile`.
- SQL lives here and nowhere else. `bl/` never imports `psycopg`.
- Employee personal details are never written to logs.
