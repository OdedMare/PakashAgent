# Frontend (`frontend/`)

Next.js App Router, TypeScript, plain CSS. Deps and conventions ported from
AiSummryIO.

**The look is "Aurora": Apple-calm neutrals, lit glass, deliberate colour.**
Tokens live in `src/styles/tokens.css`; the finish that spends them lives in
`src/styles/aurora.css`, imported last so it sits over every surface. Apple
grays and the system face (SF Pro / SF Hebrew on Apple devices, Inter and
Noto Sans Hebrew elsewhere), a canvas lit by a soft `--aurora` wash rather
than blank white, and frosted `--glass` chrome — the sidebar, the chat drawer,
the composer, dialogs — so the canvas reads through the edges. Colour has
jobs: system blue `--primary` is the next action (filled controls use
`--primary-fill`, which stays deep enough in dark mode for white text to clear
4.5:1); the blue→indigo→violet→rose `--brand-gradient` marks the agent (the
composer's focus ring, the send button, the empty-chat heading); **gold marks
the product, משמרות זהב** — `--gold-gradient` paints every `.brand-mark` (with
a dark `--on-gold` glyph, since white on gold fails contrast), `.brand-name`
is the wordmark each header stacks over the workspace name, `src/app/icon.svg`
is the favicon, and a warm gold wash sits in a corner of `--aurora`. Gold is
identity, never status: it stays off the board, where amber means warning;
and four area hues (`--hue-blue|violet|teal|pink` plus `-soft`)
tint the nav, the drawer tabs, the chat starters and every row of stat tiles
by position. Warning, danger and success are **not** area hues — they stay
reserved for schedule meaning, so amber on the board always means "look at
this". There is no navy chrome outside the tutorial page.

`next.config.ts` proxies `/api/*` to FastAPI, so the browser sees one origin
and there is no CORS setup.

## Shape

Chat-first. The boss talks to the agent in a conversation pane; the schedule
renders beside it as a grid.

The calendar is editable, but its gestures behave differently on purpose —
and the third of them is not an edit at all:

- **Dragging an assignment writes nothing.** The drop opens a confirmation
  that collects the manager's reason, and that dialog is what applies the move
  ([D12](../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).
  Dragging is a faster way to say what you want, not a way around saying why
  ([D3](../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-),
  [D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).
- **Filling an empty cell writes immediately** — the `+` on a cell opens an
  employee picker and the choice is saved
  ([D18](../docs/DECISIONS.md#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)).
  A drag moves somebody who is already placed; filling a gap takes nothing
  away from anybody, so nothing is owed an explanation. This is what lets the
  boss build a week without the agent at all.
- **Dragging a shift *row* writes nothing at all** — it is not a third
  gesture on the schedule but a change to the order the board is read in
  (`Board/shiftOrder.ts`). The rows default to **the clock**, earliest start
  first, because that is the sequence the day actually happens in; the order
  the slots were written in carried no meaning a manager could see, and
  alphabetising would scramble the same sequence differently
  ([D9](../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)). A shift
  with no hours cannot be placed on a clock, so those keep their declared
  order and sit last. The manager can drag or nudge the rows into any other
  order, remembered per browser, and put them back with one click. Because
  nothing is written, this works on a published board too, where every write
  is refused.

**A day column says whose closure it is.** `schedule.closures` arrives with
the period, computed by `bl/rotation.py`, and the board renders it on the
column head and in the placement dialog. It is not derived here on purpose:
which group closes on 12/09 is arithmetic, and a browser-side cycle would be
a second answer to a question that must have exactly one. The Sunday a
closure hands over on reads dimmer and says `חילוף` — the group is in for
that morning and out for the rest of the day.

**Taking a week back is two different acts.** *ניקוי* empties the
assignments and keeps the shift rows, so the week can be filled in again
immediately; *מחיקה* removes the period and returns the week to the state
where it offers to be built. Both go through one confirmation that counts
what is going and says which of the two it is, and the reason on it is
offered rather than required — clearing a day the agent just built takes
nothing from any one person, so there is nobody for a reason to be owed to
(D8/D18). Both are withheld on a published board and while a build is
running on the period.

**Every person has a colour**, assigned from the roster's own order and
computed in `Management/palette.ts`. It is a rendering of a name, not a stored
fact: nothing persists it, and there is no colour picker. Hues come from
position in the roster rather than a hash of the name, because ten names
hashed into ten buckets collide about two thirds of the time — a better hash
does not fix that, a different index does. A name the roster no longer carries
falls back to a hashed hue so a departed employee's past shifts stay coloured.
Every hue clears 4.5:1 in both themes and avoids the warning and danger
colours, which mean something specific on this grid.

**A board card says who is standing there, not why** (`Board/ShiftCard.tsx`).
Name, role, rotation — `exit_pattern` and `rotation_group` rendered as one
phrase by `Board/person.ts`, since a group is what makes somebody rotate at
all — plus badges for **מפקד/ת** and **נחפף/ת**. The command badge reads off
the *person*, not `slot.requires_shift_manager`: whether anyone in a cell can
run the shift is the question, and gating it on the slot hid the answer on
exactly the shifts nobody had declared it needed. `assignment.reason` used to
hold the card's last line; it is still written on every path and still
[D8](../docs/DECISIONS.md#d8--two-reasons-both-required)'s record, and it is
one hover away — but a justification is read once, when the placement is made,
and the grid is read every day.

Built so far: the workspace gate, the interview, the management area, and the
import screen. All surfaces exist.

| Surface | Purpose |
|---|---|
| Workspace gate | Pick the team, then the manager or worker door — `src/components/Workspace/`. No team creation here (D28) |
| Operator console | `/admin` — צוות משמרות זהב: every team with its counts, open (name + password)/rename/suspend/delete, the system settings — `src/components/Admin/` |
| Member area | The employee's read-only surface — `MemberArea.tsx` |
| Interview | The intro conversation, one question per turn — `src/components/Interview/` |
| Management | The manager's control room — `src/components/Management/` |
| Schedule | The living grid for a period, RTL — `Management/Calendar.tsx` |
| Manager chat | **The** agent: every instruction, question and plan, optionally focused on one day — `Management/AgentChat.tsx` |
| Change confirm | The agent's reasoning plus resulting warnings — `Management/AgentChat.tsx`, `Board/ConfirmDrop.tsx` |
| Copilot inbox | Durable observations, proposals, failures, permissions and audit — `Management/CopilotInbox.tsx` |
| Preferences | What the agent remembers, all of it visible — `Management/Preferences.tsx` |
| Import confirm | Inferred interpretation, confirmed before anything is stored — `Management/ImportSchedule.tsx` |
| Employee view | **Read-only** schedule — `MemberArea` renders the same `Calendar` with `readOnly` |
| Personal area | One employee's own shifts, constraint requests and swaps — `src/components/Employee/` |
| Employee assistant | Swap and "better week" questions; suggests checked swaps, never writes (D27) — `Employee/AssistantChat.tsx` |
| Request inbox | The manager ruling on submissions — `Management/RequestInbox.tsx` |

## Importing a schedule the workplace already had

`Management/ImportSchedule.tsx`, opened from the toolbar. Two screens, and the
split is the decision
([D7](../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)): reading
files calls `previewImport`, which **writes nothing**, and the confirm button
is the only thing that persists. The screen says so outright, because a filled
interpretation otherwise looks like a completed result.

**There is no template, and the screen says that before the first click.** A
manager who has been asked for one by other software will go looking for it
here. The importer infers axis semantics, so shifts-in-rows, people-in-rows,
and a bare list of dates and names are all readable.

**Where the file named no shift, the screen asks.** A `date_only` sheet
imports with an empty shift name and the confirm button stays disabled until
one is chosen — filling it in with a guess is exactly the hardcoding
[D9](../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace) forbids, and
a disabled button is how the question stays visible.

**Learned rules arrive unticked.** Each candidate shows the count behind it,
so the manager approves a claim they can check rather than one they must
trust. Nothing is ticked by default: a candidate becomes a rule by being
chosen, never by having been proposed.

## The management area

`Management/index.tsx` is where the manager lands once the interview has produced
a profile — `workspace.profile` is the switch, since it is the interview's
durable result and exactly the thing the area needs to run on. That profile
may be **partial** (D22), and the area says so rather than hiding it: a badge
on the interview button counts the open topics, and the empty-week card
explains that the agent is working from what it managed to learn. The manager
can ask the agent directly — `profile_gaps` is a tool like any other, so
*"מה עוד חסר לך"* is answered from the record rather than the model's
impression.

- **One gap stops the board, and it is not a policy choice.** With no shift
  vocabulary there are no rows to build from, by hand or otherwise, because
  inventing shift names is what D9 forbids. `EmptyWeek` says that instead of
  rendering an empty grid with a disabled button.

- **Drag proposes; the dialog writes.** `Calendar` reports a drop upward and
  changes nothing itself. `ConfirmDrop` collects the manager's reason and its
  confirm button stays disabled until there is one, so the requirement is
  visible rather than enforced by a server error afterwards.
- **The manual writes are deliberately quiet.** `assign` and `unassign` pass
  `{ quiet: true }` to `run()`, which skips the briefing a write normally
  triggers. A manager placing twenty people into an empty week would otherwise
  fire twenty model calls, on a deployment whose model is small and
  rate-limited — and the agent would be remarking on a grid it is watching
  being typed. The audit still runs on every one of those writes, because it
  is pure arithmetic and costs nothing, so the warnings under the calendar
  stay live throughout. Opening a blank period is *not* quiet: it happens once
  and is worth a remark.
- **One saved conversation, followed by a separate approval.** `AgentChat`
  and `useManagerChat` use `/api/agent/chats` for questions, changes, profile edits
  and actual generated previews. Follow-up questions and chosen replacements
  use saved transcript context. A question has no Apply button; a pending plan
  shows concrete changes, reasoning and all warnings. Displayed exceptions
  require an explicit checkbox before approval. Superseded plans cannot apply.
- **History is private to the signed manager browser identity.** The existing
  team-password login remains. New chat, history, deletion, polling and Stop are
  built into the conversation. Histories do not sync across devices without
  individual manager accounts. See [Manager chat](../docs/MANAGER_CHAT.md).
- **The conversation has its own available height.** Its transcript scrolls
  independently and its composer stays visible.
- **The manager owns the split between the agent and the board.** On desktop
  a visible grip on the divider drags it (arrows nudge, Home/End go to the
  limits, double-click or Enter resets). `Management/useChatSplit.ts` keeps it
  as a *share* of the workspace rather than pixels, so a split chosen on a
  wide monitor still means the same thing on a laptop, and keeps each side
  above a pixel floor (agent 340, board 320). Remembered per browser, like
  the shift-row order; nothing is written to the server. The X at the end
  of the drawer's tab row closes the agent outright, and the board takes the
  full width back — full-size cards, roles and the week rail return.
  The autonomous copilot console lives under Overview, and the old invisible
  automatic briefings are disabled for the conversation surface.
- **Export downloads; it does not navigate.** `downloadSchedule` fetches the
  binary with the session cookie and triggers the browser's own download from
  an object URL, so a failure surfaces as a Hebrew error rather than a blank
  tab ([D17](../docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).
  It is the one management action that does *not* go through `run()` — a
  download changes nothing for a refetch or a briefing to react to.
- **Building a period does not lock the area.** `generate` and its two
  siblings report through `state.generating`, never through `state.busy`:
  a build runs for minutes, and routing it through the helper the board's own
  controls wait on left the manager unable to place a single shift — or to
  reach the button that stops it — until it finished, which for a hung model
  meant forever. While a build runs the board is fully writable (D18), and a
  cell filled in by hand becomes a pin the agent fills around.
- **The poll ends, and says why.** `resumeScheduleGeneration` reads
  `/{id}/progress` rather than the whole period, backs off while one day is
  in flight, and re-fetches the grid only when a day lands. It watches the
  job's `heartbeat`: one that stops means the job lost its worker, and the
  poller re-POSTs `/run` to adopt it. Everything else is the manager's call —
  "עצירת היצירה" stops the wait *and* the job, keeping every finished day,
  because with no model timeout configured the browser is the only
  participant that knows whether anyone is still waiting.
- **Every hand-write names the period it happened on.** `assign`, `unassign`
  and `move` all send `schedule_id`, taken from the week the board is
  actually rendering. Without it the server resolves "the period covering
  today", so the moment the manager paged to another week every placement,
  drag and removal was refused — while `check`, the one call that always sent
  the id, had just told them the cell was fine. `focusPeriod` reports the
  same period upward so the agent's proposals, answers and simulations are
  about the week on screen rather than about today's.
- **The banner says how wide the build is.** `generation.mode` is stamped by
  the server when the period is opened, and a `week` build says so under the
  counter. It is the single biggest factor in how long the manager is about
  to wait, and the setting that governs it (הגדרות ← בניית סידור) lives two
  screens away — so the board states it rather than leaving them to infer it
  from the pace.
- **A failed build says why.** The per-day `error` is rendered in the banner.
  It is usually the one thing the manager can act on — a model timeout is
  fixed by a setting, not by pressing retry again.
- **Everything re-reads after a write.** `useManagement` refetches the overview
  rather than patching locally: the schedule, its warnings, the constraints and
  the log all move together, and a locally patched grid beside a stale audit is
  worse than a brief spinner.
- **One agent surface.** The manager chat is the only place the agent takes
  instructions. The board's per-day "סוכן ליום" button opens the chat focused
  on that date (sent as `focus_date`) rather than a separate dialog; a plan
  for that day rebuilds only that day. There are no automatic briefings,
  answer cards or simulation panels beside it.
- **Questions and actions share one composer.** Message requests prepare answers
  or plans and never perform domain writes. Only the separate Apply endpoint
  commits the stored plan, with snapshot checks and an atomic transaction.
  The legacy `/ask` and `/changes/propose` routes remain available to other callers.
- **Every stored preference is on screen.** `Preferences` lists suggested,
  active and archived rows and lets the manager reword, approve, archive or
  delete any of them — a preference they cannot see is a rule they never
  agreed to (D21).
- **Constraints show their source.** `source` says whether the manager decided
  it, the agent recorded it, or it came from the employee — an approved
  submission is stored as `employee_reported`, keeping "Dana said she cannot
  do Thursdays" distinct from "the manager decided Dana is off Thursdays"
  (D13/D14).
- **Approving is one click; rejecting requires a reason.** `RequestInbox`
  keeps the reject button disabled until there is one, mirroring `ConfirmDrop`
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
- **The front door asks for the team, then manager or worker**
  (`Login.tsx`, [D25](../docs/DECISIONS.md)). The worker door takes a
  *typed* name and a passcode and only signs in to a name already claimed;
  claiming still goes through the share link's `IdentityGate`. Do not put a
  roster picker here: this page is public, and a picker would publish every
  team's names.
- **Teams are opened at `/admin`, not here** ([D28](../docs/DECISIONS.md)).
  The gate says so and links to the console. The console has its own
  HttpOnly cookie, so an operator can also be signed in to a team in the same
  browser; `useAdmin` asks `/api/admin/me` for the same reason `useWorkspace`
  asks `/me`. Its "מערכת" tab renders `SystemSettings`, which unlocks on the
  operator session with no settings password. Opening a team asks for a name
  and a password only — headcount is the manager's — and that password is
  shown once on the hand-over card and never again.
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

- **The interview can always be left.** The door icon ends it early, behind a
  confirmation that states what is being left unfinished and never disables
  its own button ([D22](../docs/DECISIONS.md#d22--the-interview-can-be-ended-early-and-the-profile-says-what-it-owes-️-amends-d18)).
  This is supplied on a *first* interview too — it used to be withheld so
  nobody reached the board with nothing to schedule against, which made the
  first interview a room with no door. Ending awaits the write and then
  refreshes the workspace, because the profile it writes is what the router
  switches on; navigating first would race it.

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
- **The personal area leads with what changed.** `ChangeAlert` renders only
  when something moved since this person last acknowledged, and pressing
  "ראיתי" is what marks it read
  ([D16](../docs/DECISIONS.md#d16--an-employee-is-told-what-changed-and-acknowledging-is-what-marks-it-read)).
  `is_new` is computed server-side against their own acknowledgement — local
  state could disagree with the server and would reset on every device. A
  failed acknowledge leaves the badge standing, which is the safe direction:
  an unread change shown twice costs nothing, one silently cleared costs the
  feature.
- **The personal area (`Employee/`) mutates nothing but its own requests**
  ([D14](../docs/DECISIONS.md)). It renders the same `readOnly` `Calendar`
  with no `onDrop`. Submitting a constraint creates a **pending request** and
  the copy says so — an employee who believes a submitted constraint is
  already in force is the failure mode this feature would otherwise create.
- **The employee sees no team charts** (D27). Hours per colleague are the
  manager's stats; the personal area has the assistant instead. A suggested
  swap's button sends the ordinary `proposeSwap`, and its card says the
  colleague and the manager still have to agree.
- Import and change are two-step: interpretation/proposal, then confirmation.
  Never auto-confirm either.
- The agent's reasoning is shown before the boss confirms — it is the point, not a
  detail to hide behind a disclosure triangle ([D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).
- Shift names come from the API. No hardcoded Hebrew shift labels.
