# Frontend (`frontend/`)

Next.js App Router, TypeScript, plain CSS. Deps and conventions ported from
AiSummryIO; the design tokens in `src/styles/tokens.css` are its `shell.css`
palette — warm cream ground, terracotta accent — so the two products read as
one system.

`next.config.ts` proxies `/api/*` to FastAPI, so the browser sees one origin
and there is no CORS setup.

## Shape

Chat-first. The boss talks to the agent in a conversation pane; the schedule
renders beside it as a grid.

There is no schedule *editor*. The calendar does let the manager **drag** an
assignment, but the drop writes nothing — it opens a confirmation that collects
their reason, and that dialog is what applies the move
([D12](../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).
Dragging is a faster way to say what you want, not a way around saying why
([D3](../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-),
[D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).

Built so far: the workspace gate, the interview, and the management area. Only
the import screens remain.

| Surface | Purpose |
|---|---|
| Workspace gate | Boss login / team creation — `src/components/Workspace/` |
| Member area | The employee's read-only surface — `MemberArea.tsx` |
| Interview | The intro conversation, one question per turn — `src/components/Interview/` |
| Management | The manager's control room — `src/components/Management/` |
| Schedule | The living grid for a period, RTL — `Management/Calendar.tsx` |
| Change confirm | The agent's reasoning plus resulting warnings — `Management/AgentChat.tsx`, `ConfirmMove.tsx` |
| Import confirm | Inferred interpretation beside the raw sheet *(not built)* |
| Employee view | **Read-only** schedule — `MemberArea` renders the same `Calendar` with `readOnly` |
| Personal area | One employee's own hours, shifts and constraint requests — `src/components/Employee/` |
| Request inbox | The manager ruling on submissions — `Management/RequestInbox.tsx` |

## The management area

`Management/index.tsx` is where the manager lands once the interview has produced
a profile — `workspace.profile` is the switch, since it is the interview's
durable result and exactly the thing the area needs to run on.

- **Drag proposes; the dialog writes.** `Calendar` reports a drop upward and
  changes nothing itself. `ConfirmMove` collects the manager's reason and its
  confirm button stays disabled until there is one, so the requirement is
  visible rather than enforced by a server error afterwards.
- **The agent chat is two-step.** A proposal renders the agent's reasoning in
  full, plus the warnings the change *would* cause, and nothing is applied until
  the manager confirms. A proposal that comes back `needs_reason` carries no
  operations — the agent is asking why, and the answer goes back through the
  same call.
- **Everything re-reads after a write.** `useManagement` refetches the overview
  rather than patching locally: the schedule, its warnings, the constraints and
  the log all move together, and a locally patched grid beside a stale audit is
  worse than a brief spinner.
- **Constraints show their source.** `source` says whether the manager decided
  it, the agent recorded it, or it came from the employee — an approved
  submission is stored as `employee_reported`, keeping "Dana said she cannot
  do Thursdays" distinct from "the manager decided Dana is off Thursdays"
  (D13/D14).
- **Approving is one click; rejecting requires a reason.** `RequestInbox`
  keeps the reject button disabled until there is one, mirroring `ConfirmMove`
  — the requirement is visible rather than arriving as a server error.

## Workspaces

`src/components/Workspace/index.tsx` picks the surface from the role the
server reported: no session → the login gate, `member` → `MemberArea` (with a
door into the personal area), `employee` → the personal area, `boss` → the
interview until the workplace has been taught, then the management area.
`workspace.profile` is what switches those last two, and reopening the interview
over an existing profile is a deliberate choice the manager makes — re-running it
replaces the profile everything downstream reads.

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

- **`MemberArea` exposes no mutation.** The share link carries no identity
  (D10), so there is nothing to scope a personal view by and nobody to
  attribute a submission to — that is the decision, not an unfinished screen.
- **The personal area (`Employee/`) mutates nothing but its own requests**
  ([D14](../docs/DECISIONS.md)). It renders the same `readOnly` `Calendar`
  with no `onDrop`. Submitting a constraint creates a **pending request** and
  the copy says so — an employee who believes a submitted constraint is
  already in force is the failure mode this feature would otherwise create.
- Import and change are two-step: interpretation/proposal, then confirmation.
  Never auto-confirm either.
- The agent's reasoning is shown before the boss confirms — it is the point, not a
  detail to hide behind a disclosure triangle ([D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).
- Shift names come from the API. No hardcoded Hebrew shift labels.
