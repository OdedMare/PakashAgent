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
- `bl/schedule_service.py` — persistence and ordering around those three plus
  the audit: propose, confirm, apply, publish, constraints, history.
- `bl/audit.py` — **pure Python, no LLM.** Recomputes countable facts and returns
  warnings. Never blocks.
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
- **A dragged shift is a proposal, not an edit.** `POST /api/schedule/move`
  requires the manager's reason exactly as a spoken change does ([D12](../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).
- **An import is never committed before confirmation.** Inference produces an
  interpretation the boss approves; only then does anything persist ([D7](../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)).
- **Employees are read-only.** No endpoint lets an employee mutate a schedule ([D5](../docs/DECISIONS.md#d5--employees-are-read-only)).
  Enforced by `guards.boss()` on every mutating route — not by convention.
- **Every workplace-owned read is scoped by `team_id`, taken from the signed
  session cookie** and never from the request ([D10](../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).
- **`PAKASH_SESSION_SECRET` must be set in any real deployment.** Unset, each
  worker signs with its own key and rejects the others' cookies.
- **The change log is append-only.** The schedule is edited in place; its history
  lives only in the log ([D4](../docs/DECISIONS.md#d4--living-schedule-not-versioned)).
- Errors leaving the backend are `AgentError` in Hebrew.
- Never log API keys or full prompts containing employee personal details.
- Keep the design simple: add a module only when it owns a distinct boundary.
