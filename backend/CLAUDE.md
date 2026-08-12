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
- `dal/database/postgres.py` — connection and schema creation.
- `dal/llm/` — the OpenAI-compatible JSON client and its degradation ladder,
  ported unchanged from AiSummryIO. Model/base URL/API key stay live per call.
- `dal/repository/` — the only SQL owner.
- `bl/interview.py` — the intro interview. Collects the workplace profile,
  employees, rules (tagged hard/soft), and the **shift vocabulary**.
- `bl/scheduler.py` — generates a schedule; every assignment carries a reason.
- `bl/changes.py` — conversational edits; asks for the boss's reason, proposes a
  replacement with justification, applies on confirmation.
- `bl/audit.py` — **pure Python, no LLM.** Recomputes countable facts and returns
  warnings. Never blocks.
- `bl/importer.py` — Excel/doc ingest with layout inference.
- `bl/prompts/` — prompt text as markdown, loaded by `prompts.load(name)`.
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
- **An import is never committed before confirmation.** Inference produces an
  interpretation the boss approves; only then does anything persist ([D7](../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)).
- **Employees are read-only.** No endpoint lets an employee mutate a schedule ([D5](../docs/DECISIONS.md#d5--employees-are-read-only)).
- **The change log is append-only.** The schedule is edited in place; its history
  lives only in the log ([D4](../docs/DECISIONS.md#d4--living-schedule-not-versioned)).
- Errors leaving the backend are `AgentError` in Hebrew.
- Never log API keys or full prompts containing employee personal details.
- Keep the design simple: add a module only when it owns a distinct boundary.
