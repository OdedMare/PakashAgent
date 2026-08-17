# HTTP layer (`app/api/`)

Pydantic contracts and routers. No business logic — routers call `bl/` and shape
the result.

## Routers

Built so far: `interview.py`, `health.py`. The rest arrive with their `bl/`
modules.

| Router | Serves |
|---|---|
| `interview.py` | The intro interview, one turn at a time |
| `schedules.py` | Read a period, generate a schedule |
| `changes.py` | Propose a change, confirm a change |
| `imports.py` | Upload a file, return the inferred interpretation, commit on confirm |
| `employees.py` | Roster management |
| `health.py` | Liveness |

## The interview contract

`POST /api/interview` opens a session and returns its first question.
`POST /api/interview/{id}/answer` records an answer and returns the next
question — or `status: "complete"` with the confirmed profile.
`GET /api/interview/{id}` re-serves the pending question and **costs no model
call**: a refresh must not re-ask the model, because the same conversation
would come back differently worded and the boss would see their answered
question replaced by a near-duplicate.

The answer body carries the option's **label**, never its index. A bare number
is ambiguous by design — it may be a choice or a real value like a headcount —
and `bl/prompts/interview.md` instructs the model to ask rather than guess.
Sending "2" would manufacture exactly that ambiguity.

## The two-step contracts

Two flows are deliberately **two calls**, not one:

- **Import** — `POST` the file returns an *interpretation*, persisting nothing.
  A second call commits it. Never collapse these ([D7](../../../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)).
- **Change** — proposing returns the agent's reasoning and the resulting warnings.
  A second call applies it. The boss confirms in between ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).

## Audit warnings in responses

Any response carrying a schedule also carries `warnings` from `bl/audit.py`. They
are **advisory** — a response with warnings is still a success, still `200`, and
the schedule is still valid to display. Do not turn a warning into a `4xx`
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

## Rules

- **The employee view is read-only.** Whatever route serves employees exposes no
  mutation ([D5](../../../docs/DECISIONS.md#d5--employees-are-read-only)).
- A change request without the boss's reason is answered by *asking for it*, not
  by rejecting the request.
- Errors are `AgentError` in Hebrew, rendered for a Hebrew RTL client.
- No SQL here, and no model calls here — routers delegate to `bl/`.
