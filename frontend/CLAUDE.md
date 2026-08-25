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

**Every person has a colour**, assigned from the roster's own order and
computed in `Management/palette.ts`. It is a rendering of a name, not a stored
fact: nothing persists it, and there is no colour picker. Hues come from
position in the roster rather than a hash of the name, because ten names
hashed into ten buckets collide about two thirds of the time — a better hash
does not fix that, a different index does. A name the roster no longer carries
falls back to a hashed hue so a departed employee's past shifts stay coloured.
Every hue clears 4.5:1 in both themes and avoids the warning and danger
colours, which mean something specific on this grid.

Built so far: the workspace gate, the interview, the management area, and the
import screen. All surfaces exist.

| Surface | Purpose |
|---|---|
| Workspace gate | Boss login / team creation — `src/components/Workspace/` |
| Member area | The employee's read-only surface — `MemberArea.tsx` |
| Interview | The intro conversation, one question per turn — `src/components/Interview/` |
| Management | The manager's control room — `src/components/Management/` |
| Schedule | The living grid for a period, RTL — `Management/Calendar.tsx` |
| Change confirm | The agent's reasoning plus resulting warnings — `Management/AgentChat.tsx`, `ConfirmMove.tsx` |
| Briefing | What the agent noticed unprompted — `Management/Briefing.tsx` |
| Copilot inbox | Durable observations, proposals, failures, permissions and audit — `Management/CopilotInbox.tsx` |
| Agent answer | What the agent found when *asked* — `Management/AgentAnswer.tsx` |
| Simulation | A change being considered, never one that landed — `Management/SimulationPanel.tsx` |
| Preferences | What the agent remembers, all of it visible — `Management/Preferences.tsx` |
| Import confirm | Inferred interpretation, confirmed before anything is stored — `Management/ImportSchedule.tsx` |
| Employee view | **Read-only** schedule — `MemberArea` renders the same `Calendar` with `readOnly` |
| Personal area | One employee's own hours, shifts and constraint requests — `src/components/Employee/` |
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
  changes nothing itself. `ConfirmMove` collects the manager's reason and its
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
- **The agent chat is two-step.** A proposal renders the agent's reasoning in
  full, plus the warnings the change *would* cause, and nothing is applied until
  the manager confirms. A proposal that comes back `needs_reason` carries no
  operations — the agent is asking why, and the answer goes back through the
  same call.
- **A proposal that is asking does not look like one that is proposing.**
  `needs_input` means the agent could not tell which person, shift or date the
  request meant and asked instead of picking one. The card renders dashed with
  no confirm button, because there is nothing to confirm — a question styled
  like a proposal invites the manager to look for a button that deliberately
  is not there.
- **The manager answers the question, not the whole request again.**
  `pending_request` comes back with the question and `useManagement` sends it
  with their next sentence, so "ערב" resumes "תשבץ את דניאל". Held in a ref
  rather than state — it is sent, never rendered — and in *two* refs, one per
  conversation: a clarification about a question must never resume a held
  change, which is the one way this could target the wrong record. Dismissing
  either card clears its pending request, since the manager declining to
  answer means their next sentence is a new request.
- **The agent speaks first, and still writes nothing.** `Briefing` renders
  what the agent noticed on its own — on open, after every write, before
  publishing, and every half hour in an idle room
  ([D15](../docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).
  Clicking a suggestion **types the sentence into the composer**; the manager
  still sends it and still confirms with a reason. A briefing carries no
  operations at all, so there is nothing here that could apply itself. A quiet
  briefing renders as one calm line rather than vanishing — "I looked and it is
  fine" is worth reading, and hiding it would leave the manager unsure the
  agent looked.
- **A briefing never breaks the screen.** It has its own `busy` flag and never
  sets `error`: a failure means the agent has nothing to say, not that the
  manager's action failed. `brief()` never throws.
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
- **A failed build says why.** The per-day `error` is rendered in the banner.
  It is usually the one thing the manager can act on — a model timeout is
  fixed by a setting, not by pressing retry again.
- **Everything re-reads after a write.** `useManagement` refetches the overview
  rather than patching locally: the schedule, its warnings, the constraints and
  the log all move together, and a locally patched grid beside a stale audit is
  worse than a brief spinner.
- **Five card states, and they never look alike.** The side column
  distinguishes an *insight* (`Briefing`, the agent volunteered it), an
  *answer* (`AgentAnswer`, the agent read the schedule and reported), a
  *simulation* (`SimulationPanel`, dashed and in its own colour — nothing
  has been written), a *proposal awaiting approval* (`AgentChat`, with a
  confirm button and a required reason), and an *error*. A simulation that
  looked like a proposal would be one.
- **Asking and requesting a change are two buttons.** The magnifier calls
  `/ask` — read-only, and the card it produces has no confirm button because
  the response carries no operations (D19). Send asks the agent to propose.
  Collapsing them would make every question produce a confirm button for
  something the manager did not ask for.
- **An answer says which checks it rests on.** `AgentAnswer` lists the tools
  that ran, and states when it was produced without a model. Both are
  product requirements rather than debugging output: an answer whose checks
  are invisible has to be taken on faith, and a manager who cannot tell they
  are on the deterministic path would read "לא הבנתי" as the product being
  broken rather than the model being unconfigured.
- **Approving a simulation is the ordinary apply call.** `SimulationPanel`
  keeps its button disabled until there is a reason, mirroring `ConfirmMove`
  — and it sends the same `applyChange` a typed sentence does. There is no
  shortcut, because a second write path is how the confirmation step gets
  routed around (D8/D12).
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
- Import and change are two-step: interpretation/proposal, then confirmation.
  Never auto-confirm either.
- The agent's reasoning is shown before the boss confirms — it is the point, not a
  detail to hide behind a disclosure triangle ([D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).
- Shift names come from the API. No hardcoded Hebrew shift labels.
