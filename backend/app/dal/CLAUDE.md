# Data access (`app/dal/`)

Fetches and sends. Makes no decisions — those live in `bl/`.

- `database/postgres.py` — connection and schema creation.
- `llm/` — the OpenAI-compatible JSON client. See [llm/CLAUDE.md](llm/CLAUDE.md).
- `repository/` — the only SQL owner in the codebase.

## Tables

| Table | Holds |
|---|---|
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
