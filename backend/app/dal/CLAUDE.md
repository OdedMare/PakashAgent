# Data access (`app/dal/`)

Fetches and sends. Makes no decisions — those live in `bl/`.

- `database/postgres.py` — connection; verifies the schema exists (never creates it).
- `llm/` — the OpenAI-compatible JSON client. See [llm/CLAUDE.md](llm/CLAUDE.md).
- `repository/` — the only SQL owner in the codebase.

## Tables

Built so far: `interview_sessions` and `interview_turns` (in `schema.py`). The
rest below are the planned model, not yet created.

`schema.py` commits after each independent block. That is not cosmetic: the
whole script is sent as one simple-query message, which Postgres wraps in a
single implicit transaction, so without the checkpoints one failing guarded
migration rolls back every unrelated statement that already succeeded in the
same call. Add a new guarded migration after its own `COMMIT`.

| Table | Holds |
|---|---|
| `interview_sessions` | One intro interview: status, the confirmed profile, the pending question |
| `interview_turns` | Each turn; assistant turns keep the options they offered as `payload` |
| `workplace_profile` | What the job is, the mission, the **shift vocabulary** (names, times, on-call flags and weighting) |
| `employees` | People, with whatever roles/qualifications the interview surfaced |
| `rules` | The boss's own sentences, each tagged hard or soft |
| `shifts` | Slot definitions per period, named from the workplace vocabulary |
| `assignments` | person → shift, **with the agent's reason** |
| `schedules` | One living schedule per period |
| `change_log` | **Append-only**: what changed, the boss's reason, when |
| `availability` | Known unavailability, including what an import inferred |
| `conversations` | Interview and chat turns |

## Rules

- **`change_log` is append-only.** Never update or delete a row. It is the only
  history the system has ([D4](../../../docs/DECISIONS.md#d4--living-schedule-not-versioned)).
- **`assignments.reason` is not nullable in spirit** — an assignment without the
  agent's reasoning defeats [D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required).
- A schedule is edited in place. There are no version rows and no rollback.
- Shift names are data, not enums — they come from `workplace_profile`.
- SQL lives here and nowhere else. `bl/` never imports `psycopg`.
- Employee personal details are never written to logs.
