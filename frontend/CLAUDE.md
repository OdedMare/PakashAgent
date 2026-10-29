# Frontend (`frontend/`)

Next.js App Router, TypeScript, plain CSS. Deps and conventions ported from
AiSummryIO.

**The look is native-inspired and restrained, following Apple's productivity apps.**
Tokens live in `src/styles/tokens.css`; the shared finish lives in
`src/styles/aurora.css`, imported last. Use Apple grays, the system face
(SF Pro / SF Hebrew on Apple devices, Inter and Noto Sans Hebrew elsewhere),
opaque working surfaces and thin separators. Translucent `--glass` is reserved
for navigation and toolbars, with an opaque fallback for reduced transparency.
System blue `--primary` identifies actions and selection; filled controls use
`--primary-fill` so white labels stay readable in both themes. Avoid decorative
colour cycling, canvas washes, gradient text and glowing shadows. Gold is
reserved for the product mark and favicon. Person colours identify employees;
warning, danger and success retain their scheduling meaning. The legacy
`--brand-gradient` and `--aurora` tokens are neutral compatibility surfaces,
not invitations to add decoration. Keep keyboard focus visible, touch controls
at least 44px, and motion short with reduced-motion support.

**The two guards are the product's characters** (`components/Crew/`, pure
SVG + CSS in `styles/crew.css`; the drawing itself is the stateless
`Crew/Guard.tsx` so the server-rendered guide page can use it). They wave on
the entrance card, patrol whatever the app waits on (`CrewStage`: a build,
the agent's working line, a screen still loading), narrate the help panel,
the first-visit tour and the `/tutorial` guide, and one of them *is* the
agent: it stands in the board's corner and opens the chat when pressed.
Which one is rolled per conversation (`randomGuard`), again whenever it
returns to the corner and every 25 seconds there, never while the chat is
open, and the chat uses that guard as its avatar, greeting and working
indicator. All motion stops under `prefers-reduced-motion`.

**Every date and time field can be picked as well as typed.** `DateInput`
adds a calendar button over the browser's own picker; `TimeInput` is typed
24-hour `HH:MM` plus a clock button with an hour/minute list (`pickers.ts`,
`styles/pickers.css`), because native time inputs have no picker in some
browsers and show AM/PM in others. Use them rather than a bare `<input
type="date|time">`.

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

**The board has four widths, and they are two kinds of screen.** The switch
beside the arrows (`Board/ViewSwitch.tsx`, arithmetic in `Board/views.ts`)
chooses יום, שבוע, שבועיים or חודש, and the arrows step by whichever is
showing.

- **Day and week are the working board.** Both sit inside one stored period,
  so every gesture above is there, aimed at it. A day is `BoardGrid` handed
  one date instead of seven — the week with six columns put away, not a
  second screen — and the rail above it keeps the other six in sight and
  moves between them.
- **Two weeks and a month are for reading** (`Board/RangeGrid.tsx`). They
  cross periods, and every write the board makes names the one period it
  lands on, so nothing there writes: a day is a button that opens that day,
  a week's label opens that week, and the period's own actions — publish,
  clear, delete, export — are withheld because there is no one period for
  them to mean. Do not add a drag here. It would be a move between two
  periods with no dialog able to say which audit it answers to
  ([D12](../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).
- **A span is one read.** `GET /api/schedule/between` returns every period
  touching the dates; `Board/span.ts` clips and joins them into an ordinary
  `Schedule`, which is what lets the index, the tiles and the filters count a
  day or a month exactly as they count a week. That joined span has no id on
  purpose — it is not something a write could be aimed at.
- **The anchor is a day, remembered per session; the view is a habit,
  remembered per browser.** Switching views never moves the anchor, so a
  month narrows to the week the manager was already in. Under the two wide
  views the anchor's week is still the period reported upward
  (`onPeriodChange`), so the agent's conversation stays about a real week.
- **A day with no period says "לא תוכנן".** That and an empty day inside a
  built week are different facts, and only the first is an invitation to
  build something.

**A day column says whose closure it is.** `schedule.closures` arrives with
the period, computed by `bl/rotation/`, and the board renders it on the
column head and in the placement dialog. It is not derived here on purpose:
which group closes on 12/09 is arithmetic, and a browser-side cycle would be
a second answer to a question that must have exactly one. The Sunday a
closure hands over on reads dimmer and says `חילוף` — the group is in for
that morning and out for the rest of the day.

**A cycle is typed once, in the team setup screen** (`ManualSetup/`, the
sliders icon). The server-wide model, solver and database settings are not
on the team screen at all: they live in the operator console's "מערכת" tab.
`ManualSetup/RotationSetup.tsx` asks three numbered questions per round and
triplet, for group א only: which weekend it closes (the anchor), which round
type — a shape from `closureShapes.ts`, named by the day the closure opens
(11/3 Thursday is the server default and stores no row; 12/2 Friday, 10/4
Wednesday, שבוע־שבוע from the Sunday handover, or typed days and times are
one undated window row) — and which weekends differ (dated window rows, one
weekend or a range, with an optional `note`). The other groups' turns and
hours are derived by the server. Under the questions, `RotationPreview`
shows the coming weekends as **the server** computes them from the unsaved
rows (`POST /api/profile/rotation-preview`), so the setup screen cannot
disagree with the board. An anchor stored for another group is shown as
א's next turn in the same cycle. Presence rules stay per group, under
"מתקדם"; the older fixed א/ב unavailability block shows only to a unit that
still has rows in it. Day cycles (11/3, 12/2, שבוע־שבוע…) are typed in
`ManualSetup/DayCycleSetup.tsx`: days on base and at home, the day group א
starts on base, when each other group starts, and hours in three layers
(cycle, group, dated change). Its four-week strip is a preview of the nominal
days only; who is home on a date is answered by the server. The whole screen
saves in one `updateProfile`. A save that
adds a soldier or a shift refits every draft ahead of today, keeping its
rows (D37); anything else applies to the next build. A shift can list
`allowed_roles` there — empty restricts nobody; otherwise only people holding
one of those roles are placed on it. A shift can also ask for a different
headcount on the weekend, and "weekend" means the round's closure — the days
one group is home, until the Sunday handover — not a fixed Friday and
Saturday. The round's type (11/3, 12/2, 10/4, שבוע־שבוע) is chosen on its
card and sets the day group א's regular closure opens (Thursday, Friday,
Wednesday, or Sunday at the handover); no row means the server's Thursday. It is saved as a staffing group
marked `closure: true` whose days are worked out per shift at save time
(the first day only for a shift still running when the closure opens, the
Sunday only for one starting before the handover).

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
all — plus badges for **מפקד/ת** and **נחפף/ת**. An overlap (נחפף/ת) card drops
the per-name hue for one shared violet with a thick inline-start bar,
diagonal stripes and a solid badge, so a trainee never reads as a filled
seat; alarm styling still wins. The command badge reads off
the *person*, not `slot.requires_shift_manager`: whether anyone in a cell can
run the shift is the question, and gating it on the slot hid the answer on
exactly the shifts nobody had declared it needed. `assignment.reason` used to
hold the card's last line; it is still written on every path and still
[D8](../docs/DECISIONS.md#d8--two-reasons-both-required)'s record, and it is
one hover away — but a justification is read once, when the placement is made,
and the grid is read every day.

**The placement dialog ranks people, not just lists them**
(`Board/ShiftEditor.tsx`, fed by `POST /api/schedule/check`). Each
candidate shows availability, rotation and an overlap badge, and the list
filters (`Board/CandidateFilters.tsx`) by name, exit pattern, rotation group,
the shift types a person may work (`eligible_shifts`, from the roster), role,
and free / closing / commander / trainer / no-overlap. The filters narrow
what the check returned; they never re-check anything. Moving without a mouse (touch, keyboard) is
`useMoveMode` / `useBoardKeys` — the same drop, the same confirmation.
`FilterBar` hides rows and never changes them; `CoverageBar` keeps reporting
the whole week from the overview's own audit figures, never a browser count.

Built: the workspace gate, unit setup, the management area, the operator
console and the employee areas. There is no intro interview any more; the
profile comes from the setup form.

| Surface | Purpose |
|---|---|
| Workspace gate | Pick the team, then the manager or worker door — `src/components/Workspace/`. No team creation here (D28) |
| Operator console | `/admin` — צוות משמרות זהב: every team with its counts, open (name + password)/rename/suspend/delete, and the system settings ("מערכת", the only place they are edited) — `src/components/Admin/` |
| Member area | The employee's read-only surface — `MemberArea.tsx` |
| Unit setup | The structured profile form — roster, shift vocabulary, staffing, rotations, rules — and what code made of each sentence (`CompiledSources.tsx`, D32) — `src/components/ManualSetup/` |
| Guide | The first-run tour, the help panel and the `/tutorial` page, narrated by the two guards — `src/components/Guide/`, `src/app/tutorial/` |
| Guards | The animated pair: entrance, waits, guide, and the agent's own face — `src/components/Crew/` |
| Management | The manager's control room — `src/components/Management/` |
| Schedule | The living grid for a period, RTL — `Management/Calendar.tsx` |
| Manager chat | **The** agent: every instruction, question and plan, optionally focused on one day; opened from the guard in the board's corner — `Management/AgentChat.tsx` |
| Change confirm | The agent's reasoning plus resulting warnings — `Management/AgentChat.tsx`, `Board/ConfirmDrop.tsx` |
| Changes tab | "שינויים" — `Management/ChangesPanel.tsx`, three actions. **החלפת משמרת**: who is out and when → covers ranked so the load spreads evenly; the picks go to the chat as a plan (D36) — `ReplacementPanel.tsx`, reads only; its wording is shared with the chat cards in `lib/replacement.ts` and read back by the server. **הוספת חייל** / **הוספת משמרת**: the roster's own `EmployeeForm`/`ShiftForm`, saved through `saveProfile`, after which the server fits the newcomer into every draft from today on, keeping the board (D37) |
| Import | A file in, in any shape (D42) — `Management/ImportSchedule.tsx`, opened from the board toolbar, an empty week, or the paperclip in the chat composer. Every correction (layout fields, an alternative reading, a name or shift mapping, a description for the agent) re-sends the file to be re-read; only its confirm stores |
| Preferences | What the agent remembers, all of it visible — `Management/Preferences.tsx` |
| Employee view | **Read-only** schedule — `MemberArea` renders the same `Calendar` with `readOnly` |
| Personal area | One employee's own shifts, constraint requests and swaps — `src/components/Employee/` |
| Request inbox | The manager ruling on submissions — `Management/RequestInbox.tsx`; a new one pops up live (`RequestToast.tsx`, pushed via `useLiveInbox.ts`, D29) |

## The management area

`Management/index.tsx` is where the manager lands once unit setup has saved
a profile — `workspace.profile` is the switch, since it is exactly the thing
the area needs to run on. A profile may still owe something (an older
partial one, D22), and the area says so rather than hiding it:
`ProfileGapsNotice` lists the gaps and points back to setup. The manager can
ask the agent directly — `profile_gaps` is a tool like any other, so
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
- **The manual writes call no model.** `assign` and `unassign` write one
  cell each and re-read the overview; `{ quiet: true }` still marks them, a
  leftover from the automatic briefings that are gone (the agent speaks only
  in the manager chat). The audit runs on every one of those writes, because
  it is pure arithmetic and costs nothing, so the warnings under the calendar
  stay live throughout.
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
- **Export downloads; it does not navigate.** `downloadSchedule` fetches the
  binary with the session cookie and triggers the browser's own download from
  an object URL, so a failure surfaces as a Hebrew error rather than a blank
  tab ([D17](../docs/DECISIONS.md#d17--a-schedule-leaves-as-a-file-a-message-is-something-the-agent-writes)).
  It is the one management action that does *not* go through `run()` — a
  download changes nothing for a refetch to react to.
- **A build can start on any day and end on any day.** "בנייה מכאן" on a
  day's column head, and "בנייה מיום … עד שבת" on the card of an unbuilt
  week, open the one build dialog (`Board/GenerateDialog.tsx`) on that day
  through Saturday; both ends stay editable and "עד שבת" is a shortcut, not
  a limit. Inside a draft that exists it is `generateScheduleRange`: only
  those days are solved, what was generated on them is replaced, and
  what the manager placed is kept and filled around (D18) — the dialog counts
  both before the click, and takes no list of required shifts because the
  board behind it already is one. "שמירה על השיבוץ הקיים" sends
  `keep_existing`: the built rows stay where they fit and only what a new
  soldier or shift needs moves (D37). The run is bounded by the period: a build
  is one job on one period. On a week with nothing stored, the period is
  still opened as **whole weeks** (`inWholeWeeks`) with the run sent beside
  it as `build_from`/`build_through`. The board finds a week by its Sunday,
  so a period beginning on a Wednesday would be stored and never drawn; the
  days outside the run open empty instead.
  The dialog also narrows a build by shift type: "כל המשמרות" or one or
  more "רק <משמרת>" buttons, named from setup. Only the chosen shifts are
  built (`shifts` on both calls); the others on those days stay as they are.
- **Building a period does not lock the area.** `generate` and its two
  siblings report through `state.generating`, never through `state.busy`:
  a build is a background job — seconds per four-week span for the solver
  (D34), longer when its sentences are translated by a slow model — and
  routing it through the helper the board's own controls wait on left the
  manager unable to place a shift, or reach the stop button, until it
  finished. While a build runs the board is fully writable (D18), and a cell
  filled in by hand becomes a pin the solver fills around.
- **The poll ends, and says why.** `resumeScheduleGeneration` reads
  `/{id}/progress` rather than the whole period, backs off while a span is
  in flight, and re-fetches the grid only when one lands. It watches the
  job's `heartbeat`: one that stops means the job lost its worker, and the
  poller re-POSTs `/run` to adopt it. Everything else is the manager's call —
  "עצירת היצירה" stops the wait *and* the job, keeping every finished span:
  the browser is the only participant that knows whether anyone is still
  waiting.
- **Every hand-write names the period it happened on.** `assign`, `unassign`
  and `move` all send `schedule_id`, taken from the week the board is
  actually rendering. Without it the server resolves "the period covering
  today", so the moment the manager paged to another week every placement,
  drag and removal was refused — while `check`, the one call that always sent
  the id, had just told them the cell was fine. `focusPeriod` reports the
  same period upward so the agent's proposals, answers and simulations are
  about the week on screen rather than about today's.
- **The banner counts days and says what the build is doing.** The counter
  is in dates however many spans the job has, and `generation.activity` is
  the worker's current step. What a build could not honour — a seat nobody
  could legally fill, a sentence that did not translate — arrives in its
  notes, not as an error (D34).
- **A failed build says why.** The span's `error` is rendered in the banner.
  It is usually the one thing the manager can act on — a pin that breaks a
  hard constraint, or the database being unreachable — not something retry
  fixes.
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
  The legacy `POST /api/schedule/propose` and `/apply` remain for other
  callers; `/ask`, `/simulate`, `/tool` and `/brief` are gone.
- **Deleting an employee is a departure, not an erasure.** The roster card's
  "הוצאה מהסגל" opens `ConfirmDeparture`, which counts first
  (`/api/schedule/departure/preview`, writes nothing): how many shifts from
  the chosen date on will be vacated, and which published weeks return to
  draft. Confirming sets `inactive_from` and vacates those shifts, each one
  logged — the chat's `retire` plan without the model. The name stays in the
  profile because it is the key history, identity and colour hang on
  (`keep_existing_names` refuses a removal outright). The person moves to
  "עובדים שסיימו", where "החזרה לסגל" clears the date; vacated shifts stay
  vacated.
- **Every stored preference is on screen.** `Preferences` lists suggested,
  active and archived rows and lets the manager reword, approve, archive or
  delete any of them — a preference they cannot see is a rule they never
  agreed to (D21).
- **The stats panel counts shifts, and its filter asks the server.**
  `Stats` reports load per person in shifts — how many, how many of them
  nights, and the person's rotation in the words a board card uses — plus
  the number of conflicts (audit findings at `warning` severity, the board
  tile's own cut). Hours are weighted, so they stay in the hover and are no
  longer what the chart is drawn in. `StatsFilter` narrows all of it to a
  day, a week, a calendar month, a chosen range, or one person; unfiltered
  it renders the overview's own `stats`, and any other choice is
  `GET /api/schedule/stats` (`useStats`). Never a `.filter()` over the rows
  on screen: those are one period, a month is several, and a second count
  in the browser is how a tile comes to disagree with the warning under it.
  Coverage is hidden for one person — a seat belongs to the slot.
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
door into the personal area), `employee` → the personal area, `boss` → unit
setup (`ManualSetup`) until the workplace has a profile, then the management
area. `workspace.profile` is what switches those last two; the sliders icon
reopens setup over an existing profile, and a save there applies to the next
build — except a new soldier or shift, which is absorbed into the drafts
ahead of today with as few moves as possible (D37). The management area
picks the refit up as a running build on mount; `saveProfile` watches the
one on screen and names any published week it left alone.

- **A lost session returns to the gate, once.** A GET refused with 401
  calls `onSessionLost` (`services/api.ts`); `useWorkspace` re-asks `/me`
  and only on its own 401 drops to the login gate, which unmounts every
  poller — otherwise they kept asking every few seconds after the cookie
  died (a restart without a fixed session secret, a suspended team).
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

## Audit warnings

Warnings render as **non-blocking inline banners** on the schedule. They never
gate a save, never block confirmation, and never present as errors. A schedule
with warnings is a valid schedule the boss may knowingly accept
([D3](../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
An overlapping operational duty is not an advisory warning: the placement
check marks it `blocking`, the confirmation action is disabled, and the server
also refuses the write.

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
  manager's stats. The employee assistant chat is gone; a swap is offered
  only through the swap form ("בקשות והחלפות", `proposeSwap`), and its card
  says the colleague and the manager still have to agree. The full-board
  tab there widens to the whole window.
- A change is two-step: proposal, then confirmation. Never auto-confirm it.
- The agent's reasoning is shown before the boss confirms — it is the point, not a
  detail to hide behind a disclosure triangle ([D8](../docs/DECISIONS.md#d8--two-reasons-both-required)).
- Shift names come from the API. No hardcoded Hebrew shift labels.
