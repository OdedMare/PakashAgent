# HTTP layer (`app/api/`)

Pydantic contracts and routers. No business logic — routers call `bl/` and shape
the result.

## Routers

| Router | Serves |
|---|---|
| `workspace.py` | Enter a workspace, the member share link, logout. Creating one is refused unless `allow_signup` (D28) |
| `admin.py` | The צוות משמרות זהב console (D28): operator sign-in, every team with its counts, open (name + password)/rename/suspend/delete a team, reset its manager password, rotate its link |
| `profile.py` | Boss-only structured unit setup, profile updates (`PUT` also starts the refit of every draft ahead of today when it adds a soldier or a shift, and returns it as `absorbed`, D37), `DELETE /shifts/{name}` — archiving a shift type (stored schedules keep their rows) — and `/compiled`, what code made of each rule and note (D32) |
| `manager_chat.py` | `/api/agent/chats` — the manager's conversations: send a message (queued as a job; an edited message replaces it and what followed), poll, stop, `regenerate` (answer the last request again in place of the last answer), apply or dismiss a pending plan |
| `replacements.py` | `GET /api/agent/replacements` — the changes tab's ranked covers for who is out and when (D36). Reads only |
| `schedules/` | `/api/schedule` — the management area. `reading.py`: the overview, the current period, the one at a date (`/at`), a span (`/between`, capped at 62 days); `statistics.py`: stats over any span. `generation.py`: solve a period now (`/generate`), or open a resumable job (`/generate/start`, `build_from`/`build_through`), run, poll `progress`, cancel, dismiss, one day (`/day/start`) or a run of days in a draft (`/range/start`); the build calls also take `shifts` (only those shift types) and the range `keep_existing` (hold the board, D37). `manual.py`: blank period, assign, unassign, check, departure (D18). `periods.py`: publish, unpublish, clear, delete, progress; `transfer.py`: export. `agent.py`: propose, apply, move (D8/D12). Constraints, history, learning and preferences (D21) |
| `settings.py` | `/api/settings` and `/api/models` — the process-wide settings and the model-list probe. The team screen no longer links to them; the operator console's "מערכת" tab is their UI |
| `health.py` | Liveness and database reachability |
| `employee/` | The employee's own area: claim an identity, read your own shifts, submit a constraint request or swap — plus the boss-guarded routers that rule on them and `GET /api/schedule/requests/events`, the manager's SSE stream that says an inbox moved (D29, across processes over LISTEN/NOTIFY, D35) |

## The two-step contracts

A change is deliberately **two calls**, not one:

- **Change** — proposing returns the agent's reasoning and the resulting warnings.
  A second call applies it. The boss confirms in between ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)).
  **A drag on the calendar is the same contract**: the gesture writes nothing,
  and `POST /api/schedule/move` is what the confirmation dialog sends once the
  manager has given a reason ([D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).

## Audit warnings in responses

Any response carrying a schedule also carries `warnings` from `bl/audit/`. They
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
- `guards.admin()` — the operator, on its own `pakash_admin` cookie (D28).
  Never satisfied by a team cookie, and a team guard is never satisfied by
  it. The console's routes are the only ones that take a team id from the
  path, because the operator acts on every team by design.
- `guards.employee()` — a signed-in employee acting as themselves
  ([D14](../../../docs/DECISIONS.md)). Admits exactly one write, a constraint
  *request*, and nothing that touches a schedule. The identity comes from
  `session["employee"]` on the signed cookie; a route that took the name from
  the body would let one employee read or act as another.

**The manual routes are one call, not two** ([D18](../../../docs/DECISIONS.md#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)).
`/blank`, `/assign` and `/unassign` write on the first call and involve no
model and no solver. That is not a collapse of the two-step contracts above: those exist so
a *change* is explained before it lands, and placing somebody in an empty
cell changes nothing for anybody. All three are `guards.boss()` like every
other schedule write.

**Route order matters in `schedules/`.** A path parameter at the root of a
prefix matches any single segment, so `/{schedule_id}` is declared *after* every
literal path under it — otherwise `/constraints` and `/history` are read as
schedule ids. FastAPI resolves in declaration order.

**The team always comes from the signed session cookie, never from the request
body or a path parameter.** A route that accepts a team id from the caller is a
route that lets one workspace name another.
The only exceptions are the two logins that *issue* that cookie,
`POST /api/workspace/login` and `POST /api/employee/signin` (D25). Each one
checks a credential for the team it names before signing anything.

`/api/settings` is process-wide — it holds the database credentials and the
model key — and admits the operator on its own session, or a boss who also
sends the settings password. See [D10](../../../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)
for why it is not per-team yet.

## Remembering

`/preferences*` are boss-only, read the team from the signed cookie, and are
fully visible (D21). A suggested preference is inert until a `PATCH` sets it
active. Questions and simulations go through the manager chat; the old
`/ask`, `/tool`, `/simulate` and `/brief` routes are gone.

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
