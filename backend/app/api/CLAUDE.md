# HTTP layer (`app/api/`)

Pydantic contracts and routers. No business logic — routers call `bl/` and shape
the result.

## Routers

Built so far: `workspace.py`, `interview.py`, `schedules.py`, `health.py`.
`imports.py` arrives with `bl/importer.py`; `changes.py` and `employees.py` were
folded into `schedules.py` rather than split, since they share the schedule and
the team scoping.

| Router | Serves |
|---|---|
| `workspace.py` | Create/enter a workspace, the member share link, logout |
| `interview.py` | The intro interview, one turn at a time |
| `schedules.py` | The management area: read/generate a period, open one blank and fill it by hand (D18), propose and apply changes, constraints, history, plus asking (`/ask`, `/tool`), simulating (`/simulate`) and preferences (D19–D21) |
| `imports.py` | Upload a file, return the inferred interpretation, commit on confirm |
| `employees.py` | Roster management |
| `health.py` | Liveness |
| `employee.py` | The employee's own area: claim an identity, read your own hours, submit a constraint request — plus the boss-guarded router that rules on them |

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
  **A drag on the calendar is the same contract**: the gesture writes nothing,
  and `POST /api/schedule/move` is what the confirmation dialog sends once the
  manager has given a reason ([D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).

## Audit warnings in responses

Any response carrying a schedule also carries `warnings` from `bl/audit.py`. They
are **advisory** — a response with warnings is still a success, still `200`, and
the schedule is still valid to display. Do not turn a warning into a `4xx`
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

## Access control

Every route states its own requirement as a dependency —
`session: dict = Depends(guards.boss())` — rather than inheriting one from a
path prefix. A middleware rule matched on a prefix is invisible at the route,
and a new route added under the wrong prefix silently inherits the wrong guard.

- `guards.visitor()` — any authenticated visitor: boss, member, or employee.
- `guards.boss()` — the boss only. **Every schedule-mutating route depends on
  it**, so neither a member nor a signed-in employee can reach a write no
  matter which URL it is pointed at.
- `guards.employee()` — a signed-in employee acting as themselves
  ([D14](../../../docs/DECISIONS.md)). Admits exactly one write, a constraint
  *request*, and nothing that touches a schedule. The identity comes from
  `session["employee"]` on the signed cookie; a route that took the name from
  the body would let one employee read or act as another.

**The manual routes are one call, not two** ([D18](../../../docs/DECISIONS.md#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)).
`/blank`, `/assign` and `/unassign` write on the first call and involve no
model. That is not a collapse of the two-step contracts above: those exist so
a *change* is explained before it lands, and placing somebody in an empty
cell changes nothing for anybody. All three are `guards.boss()` like every
other schedule write.

**Route order matters in `schedules.py`.** A path parameter at the root of a
prefix matches any single segment, so `/{schedule_id}` is declared *after* every
literal path under it — otherwise `/constraints` and `/history` are read as
schedule ids. FastAPI resolves in declaration order.

**The team always comes from the signed session cookie, never from the request
body or a path parameter.** A route that accepts a team id from the caller is a
route that lets one workspace name another.

`/api/settings` is boss-only and process-wide — it holds the database
credentials and the model key. See [D10](../../../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)
for why it is not per-team yet.

## Asking, simulating, remembering

Three route groups added with D19–D21, all `guards.boss()` and all reading
the team from the signed cookie:

- **`POST /ask` and `POST /tool` write nothing**, and `/ask`'s response type
  has **no operations field at all** — there is nothing an `apply` could read
  out of an answer, the same property `/brief` has (D15). Asking about the
  schedule and asking to change it are separate endpoints because they are
  separate acts; a question whose answer implies a change comes back with
  `needs_confirmation` and still goes through propose-then-confirm.
- **`POST /simulate` persists nothing** and returns an impact report rather
  than something confirmable. Approving one is an ordinary `POST /apply`
  with the manager's reason — there is deliberately **no** "apply
  simulation" endpoint, because a second write path is how the confirmation
  step gets routed around (D8/D12).
- **`/preferences*` are boss-only and fully visible.** A suggested preference
  is inert until a `PATCH` sets it active.

An unknown tool name on `/tool` answers `200` with `ok: false` rather than
raising: the caller is a UI that has to render something, and "there is no
such tool" is information rather than a failed request.

**These are declared before `/{schedule_id}`** like every other literal path
under this prefix — `/preferences/list` read as a schedule id is exactly the
bug the ordering note above exists to prevent.

## Rules

- **No employee route mutates a schedule.** `POST /api/employee/requests` is
  the single write an employee gets, and it creates a *pending request* that
  changes nothing until a manager approves it. Deciding requests lives on a
  separate `boss`-guarded router (`/api/schedule/requests`) so the guard is
  unmistakable at a glance.
- A change request without the boss's reason is answered by *asking for it*, not
  by rejecting the request.
- Errors are `AgentError` in Hebrew, rendered for a Hebrew RTL client.
- No SQL here, and no model calls here — routers delegate to `bl/`.
