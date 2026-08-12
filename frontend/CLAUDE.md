# Frontend (`frontend/`)

Next.js. Shell ported from AiSummryIO's `AppShell`.

## Shape

Chat-first. The boss talks to the agent in a conversation pane; the schedule
renders beside it as a grid. There is no schedule *editor* — changes happen by
talking, which is the product ([D3](../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

| Surface | Purpose |
|---|---|
| Interview | The intro conversation, one question per turn |
| Schedule | The living grid for a period, RTL |
| Import confirm | Inferred interpretation beside the raw sheet |
| Change confirm | The agent's reasoning plus resulting warnings |
| Employee view | **Read-only** schedule |

## RTL is not a theme

`dir="rtl"`, Hebrew copy, and a grid that reads right-to-left like the source
files. Hebrew is also *data* — shift names, weekdays, and availability markers all
arrive in Hebrew from the backend ([FILE_FORMATS.md](../docs/FILE_FORMATS.md)).
Never assume a Latin-script fallback.

## Audit warnings

Warnings render as **non-blocking inline banners** on the schedule. They never
gate a save, never block confirmation, and never present as errors. A schedule
with warnings is a valid schedule the boss may knowingly accept
([D3](../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

## Rules

- The employee view exposes no mutation ([D5](../docs/DECISIONS.md#d5--employees-are-read-only)).
- Import and change are two-step: interpretation/proposal, then confirmation.
  Never auto-confirm either.
- The agent's reasoning is shown before the boss confirms — it is the point, not a
  detail to hide behind a disclosure triangle ([D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).
- Shift names come from the API. No hardcoded Hebrew shift labels.
