# Frontend (`frontend/`)

Next.js App Router, TypeScript, plain CSS. Deps and conventions ported from
AiSummryIO; the design tokens in `src/styles/tokens.css` are its `shell.css`
palette — warm cream ground, terracotta accent — so the two products read as
one system.

`next.config.ts` proxies `/api/*` to FastAPI, so the browser sees one origin
and there is no CORS setup.

## Shape

Chat-first. The boss talks to the agent in a conversation pane; the schedule
renders beside it as a grid. There is no schedule *editor* — changes happen by
talking, which is the product ([D3](../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

Built so far: the workspace gate and the interview. The rest of the table is
the plan.

| Surface | Purpose |
|---|---|
| Workspace gate | Boss login / team creation — `src/components/Workspace/` |
| Member area | The employee's read-only surface — `MemberArea.tsx` |
| Interview | The intro conversation, one question per turn — `src/components/Interview/` |
| Schedule | The living grid for a period, RTL |
| Import confirm | Inferred interpretation beside the raw sheet |
| Change confirm | The agent's reasoning plus resulting warnings |
| Employee view | **Read-only** schedule |

## Workspaces

`src/components/Workspace/index.tsx` picks the surface from the role the
server reported: no session → the login gate, `member` → `MemberArea`, `boss`
→ the interview.

- **The session is an HttpOnly cookie**, so this code cannot read it. "Am I
  logged in?" is answered by `GET /api/workspace/me`, never by local state
  that could disagree with the cookie the browser actually holds.
- **`undefined` and `null` are different workspace states.** `undefined` is
  "not asked yet" and `null` is "no session" — rendering the login screen
  during the first check would flash it at a boss who is already signed in.
- **Every request sends `credentials: "same-origin"`.** Without it the browser
  withholds the cookie and every guarded route answers 401 while the user is
  plainly logged in.
- **The member share link is `/team/<token>`.** `MemberEntry` exchanges the
  token for a cookie and then `replaceState`s it out of the URL, so the
  credential stops travelling in the address bar and the back stack.
- **This routing is not the access control.** The backend guards every route
  independently; a visitor who forced past the component still gets a 401.

## RTL is not a theme

`dir="rtl"`, Hebrew copy, and a grid that reads right-to-left like the source
files. Hebrew is also *data* — shift names, weekdays, and availability markers all
arrive in Hebrew from the backend ([FILE_FORMATS.md](../docs/FILE_FORMATS.md)).
Never assume a Latin-script fallback.

## The interview surface

One question per turn, rendered as a Claude-style conversation column: the
agent's question, its recommendation in a marked-off card, and 2–5 selectable
answers beneath it.

- **Answers send the option's label, not a number.** A bare number is
  ambiguous — choice or headcount — and the prompt makes the model ask rather
  than guess. Numbering the buttons would teach the boss to answer "2".
- **Free text is a separate field, never an "אחר" option.** An option called
  "other" makes writing your own answer look like a last resort; the prompt
  forbids it for that reason.
- **A recommendation is the agent's opinion, not a workplace fact.** It is
  styled as its own card so it never reads as something the boss already said.
- **Only the newest question is answerable.** Past turns keep rendering their
  options, disabled, so the thread stays readable without letting a question
  be answered twice.
- **The session id is the only client state**, held in `localStorage`. A
  refresh resumes server-side and costs no model call.

## Audit warnings

Warnings render as **non-blocking inline banners** on the schedule. They never
gate a save, never block confirmation, and never present as errors. A schedule
with warnings is a valid schedule the boss may knowingly accept
([D3](../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

## Rules

- The employee view exposes no mutation ([D5](../docs/DECISIONS.md#d5--employees-are-read-only)).
  `MemberArea` has no edit, accept, decline, or availability control — that is
  the decision, not an unfinished screen.
- Import and change are two-step: interpretation/proposal, then confirmation.
  Never auto-confirm either.
- The agent's reasoning is shown before the boss confirms — it is the point, not a
  detail to hide behind a disclosure triangle ([D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).
- Shift names come from the API. No hardcoded Hebrew shift labels.
