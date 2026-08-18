# PakashAgent backend context

Read this before changing `backend/`.

Design decisions with their reasoning: [`../docs/DECISIONS.md`](../docs/DECISIONS.md).
Real Excel layouts: [`../docs/FILE_FORMATS.md`](../docs/FILE_FORMATS.md).

## Purpose

Turn a conversation with the boss into a maintained shift schedule. The agent
learns the workplace once (intro interview), then generates schedules, imports
ones the boss already has, and rearranges them on request — explaining every
decision and recording every reason.

## Runtime and commands

Python is **3.8.10**, mirroring AiSummryIO. Keep annotations compatible: use
`Optional`, `List`, `Dict`; do **not** use `X | Y`, `list[str]`, or `match`.
*(If the deployment target turns out to be newer, this is the one open question
in DECISIONS.md — resolve it before writing much code.)*

```bash
cd backend
python -m pytest -q
uvicorn app.main:app --reload
```

## Architecture

- `common/` — env defaults (`PAKASH_` prefix) plus the live runtime-settings
  override store. Saved settings override env without restart; secrets masked.
- `dal/database/postgres.py` — connection; verifies the schema exists.
- `dal/llm/` — the OpenAI-compatible JSON client and its degradation ladder,
  ported unchanged from AiSummryIO. Model/base URL/API key stay live per call.
- `dal/repository/` — the only SQL owner. `teams.py` also owns password
  hashing (`scrypt`, stdlib) and the member share token.
- `bl/workspace_service.py` — workspace rules: who may enter a team, in which
  role, and what a new workspace inherits.
- `api/dependencies.py` — the route guards (`visitor`, `boss`).
- `common/sessions.py` — signed session cookies (HMAC-SHA256, no library).
- `bl/interview.py` — the intro interview, one `plan-chat` turn at a time
  (ported from AiSummryIO). Collects the workplace profile, employees, rules
  (tagged hard/soft), and the **shift vocabulary**. Every turn returns the
  draft profile so far; `ready` is gated in code, never trusted to the prompt.
- `bl/scheduler.py` — generates a schedule; every assignment carries a reason.
  Builds the slot grid in code (which dates fall in a period is arithmetic) and
  asks the model only to assign people into it.
- `bl/changes.py` — conversational edits; asks for the boss's reason, proposes a
  replacement with justification, applies on confirmation. Proposes only — it is
  handed no repository, so it cannot write.
- `bl/briefing.py` — **the agent speaking first.** Reads the current state and
  says what it noticed, unprompted. Returns exactly `headline`, `items`,
  `quiet` — no operations, so there is no path from a briefing to a write.
- `bl/schedule_service.py` — persistence and ordering around those three plus
  the audit: propose, confirm, apply, publish, constraints, history.
- `bl/audit.py` — **pure Python, no LLM.** Recomputes countable facts and returns
  warnings. Never blocks. Also owns `personal_summary()` and `fairness()`, which
  the employee area renders — they live here so one person's hours are literally
  the same arithmetic as the manager's warnings, not a second implementation.
- `bl/employee_service.py` — identity claims, the personal view, constraint
  requests, and the unread-change mark. Approval is the only thing that writes
  a constraint (D14).
- `bl/export.py` — a period out as `.xlsx`. Pure functions, no model, no
  repository. Laid out shift-major like `FILE_FORMATS.md` Sample A so an
  exported week can be edited and imported back.
- `bl/importer.py` — Excel/doc ingest with layout inference.
- `bl/prompts/` — prompt text as markdown, loaded by `prompts.load(name)`.
  Shared fragments compose via `<!-- include: shared/name.md -->`.
- `api/` — Pydantic HTTP contracts and routers.
- `main.py` — FastAPI routes and composition root.

Business logic under `bl/`, data access under `dal/`. A file owns one class or
one concern; split rather than append.

## Locked rules

- **The audit never blocks.** `bl/audit.py` returns warnings and nothing else. It
  does not reject a schedule, rewrite an assignment, or veto the agent. Making it
  authoritative reverses [D3](../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)
  — the whole product shape depends on the agent keeping the judgment.
- **The audit contains no LLM call.** Its entire value is being arithmetic that
  cannot be hallucinated. Pure functions over a roster; trivially unit-testable.
- **Hard rules are not gates.** They are strong instructions to the model plus a
  loud warning when broken. This is a deliberate, accepted tradeoff — see D1/D3.
- **Shift names are never hardcoded.** They come from the interview. Any literal
  `"בוקר"` outside a test fixture or a Hebrew vocabulary table is a bug ([D9](../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
- **No structured rule vocabulary.** Rules are the boss's own sentences ([D2](../docs/DECISIONS.md#d2--rules-stay-natural-language)).
- **Every assignment carries the agent's reason**; every change carries the boss's
  reason too. Neither is optional — they serve different purposes ([D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).
  Enforced in three places on purpose: `assignments.reason` is `NOT NULL`, the
  repository refuses a blank one, and `scheduler.py` drops an unreasoned row
  rather than storing it.
- **A briefing observes; it never acts.** `bl/briefing.py` returns three keys
  and none of them is an operation, so nothing it says can be applied
  ([D15](../docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).
  A `suggestion` is a sentence the manager may send, after which the ordinary
  propose-then-confirm path runs unchanged. Giving a briefing operations that
  `apply` could read would reverse D3, D8 and D12 at once.
- **A briefing never counts.** `warnings` and `fairness` are computed by
  `audit.py` and handed to the model as facts. Speaking first does not move
  the D3 line about which side does arithmetic.
- **`schedule_service.brief()` never raises.** It returns quiet on any failure:
  it decorates a screen that must render regardless of what the model is doing.
- **A dragged shift is a proposal, not an edit.** `POST /api/schedule/move`
  requires the manager's reason exactly as a spoken change does ([D12](../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).
- **The export layout is Sample A, not a design choice.** `bl/export.py`
  writes the shape `bl/importer.py` is being built to read, so a week can
  leave and come back ([D17](../docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).
  Changing the layout to something prettier produces a file this product
  cannot read.
- **A message for the team is written by the agent, not templated in code.**
  Posting the week to a group chat is writing, and the manager asks for it in
  the conversation — the change agent answers with `reply` and no operations.
  Nothing is sent anywhere; the product has no channel to the team beyond the
  share link and holds no employee contact details.
- **An import is never committed before confirmation.** Inference produces an
  interpretation the boss approves; only then does anything persist ([D7](../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)).
- **No endpoint lets an employee mutate a schedule.** Enforced by
  `guards.boss()` on every schedule-mutating route — not by convention.
  [D14](../docs/DECISIONS.md) narrowed [D5](../docs/DECISIONS.md#d5--employees-are-read-only)
  but did **not** remove it: a signed-in employee may submit a constraint
  *request* via `guards.employee()` and nothing else. They cannot assign,
  move, publish, or approve — including their own request.
- **A pending constraint request is inert.** It lives in `constraint_requests`,
  not `availability`, so `bl/audit.py` cannot see it and submitting one cannot
  move the arithmetic. The manager's approval is what promotes it into an
  `availability` row with `source='employee_reported'` (D13/D14). Keeping the
  two tables separate is what makes that a property of the schema rather than
  a filter every reader must remember.
- **`acknowledged_at` is not `last_seen_at`.** The latter moves on every
  login, so nothing could ever be new against it; the former advances only
  when the employee acknowledges what they were shown, which is what makes
  "what changed for me" answerable ([D16](../docs/DECISIONS.md#d16--an-employee-is-told-what-changed-and-acknowledging-is-what-marks-it-read)).
  A NULL acknowledgement means **everything** is new, not nothing — otherwise
  the first notification, the one that matters most, is swallowed.
- **An acknowledgement gates nothing.** It is not consent and not an
  acceptance; the manager publishes whether or not anyone has read anything.
- **An employee's identity comes off the signed cookie, never the request.**
  `session["employee"]` scopes every personal read. A name accepted from a body
  would let any signed-in employee read a colleague's hours and stated reasons.
- **Every workplace-owned read is scoped by `team_id`, taken from the signed
  session cookie** and never from the request ([D10](../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).
- **`PAKASH_SESSION_SECRET` must be set in any real deployment.** Unset, each
  worker signs with its own key and rejects the others' cookies.
- **The change log is append-only.** The schedule is edited in place; its history
  lives only in the log ([D4](../docs/DECISIONS.md#d4--living-schedule-not-versioned)).
- Errors leaving the backend are `AgentError` in Hebrew.
- Never log API keys or full prompts containing employee personal details.
- Keep the design simple: add a module only when it owns a distinct boundary.
