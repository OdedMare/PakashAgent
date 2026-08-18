# Data access (`app/dal/`)

Fetches and sends. Makes no decisions — those live in `bl/`.

- `database/postgres.py` — connection; verifies the schema exists (never creates it).
- `llm/` — the OpenAI-compatible JSON client. See [llm/CLAUDE.md](llm/CLAUDE.md).
- `repository/` — the only SQL owner in the codebase.

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
| `interview_sessions` | One intro interview: its **team**, status, the confirmed profile, the pending question |
| `interview_turns` | Each turn; assistant turns keep the options they offered as `payload` |
| `schedules` | One living schedule per period, `draft` or `published` |
| `shift_slots` | One shift on one date — the thing an assignment points into |
| `assignments` | person → slot, **with the agent's reason** (`NOT NULL`) |
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
- A schedule is edited in place. There are no version rows and no rollback.
- Shift names are data, not enums — they come from `workplace_profile`.
- SQL lives here and nowhere else. `bl/` never imports `psycopg`.
- Employee personal details are never written to logs.
