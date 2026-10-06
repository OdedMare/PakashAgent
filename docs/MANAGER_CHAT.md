# Manager conversation on the shift board

The manager has one saved conversation for questions, recommendations and
management requests. The desktop panel opens alongside the board and can be
resized; mobile uses the existing drawer. New chat and history keep separate
conversations. Enter sends; Shift+Enter adds a line. The existing model provider,
credentials, role routing and FastAPI / business logic / PostgreSQL architecture
remain in use.

The chat is the manager's only agent surface. Each day header on the board has
a "סוכן ליום" button that opens the chat focused on that date. A chip above the
log names the day and can be cleared; paging to another week drops it. While a
day is focused every message carries `focus_date`, and the agent treats requests
that name no date as being about that day.

## What the agent can do

- Answer schedule and workload questions with the existing read-only tools,
  plus period lookup, change history and a computed workload report for a date range.
- Propose replacements, moves and swaps, including complete sickness plans
  with absence constraints, and show individual replacement selectors.
- Record availability for future dates before a schedule exists.
- Build, fill or rebuild a week as actual assignments shown before approval,
  or a single day (or a few days) inside an existing draft period. A partial
  rebuild shows the model the rest of the period, audits the whole period, and
  on approval touches only the requested dates.
  The manager can revise individual generated assignments. Filling retains all
  saved assignments; rebuilding retains placements made by the manager.
- Add or edit employees, shift definitions, the workplace and initial setup rules.
  Profile patches use the existing profile validation and show before/after values.
- Propose publishing, returning to draft or clearing a period.

The full initial profile, current availability (from a week ago, or the focused
period's start if earlier), recurring constraints, rotations, standing
preferences and recent changes accompany the conversation. Every round of one
reply re-sends that context with the same clock and the round's tool results
last, so the model server can reuse the part it already computed. Arbitrary
written policies are interpreted by the model; supported countable rules are
also checked by the existing deterministic audit. Suggestions prefer compliant
candidates. Exceptions are shown and require a separate checkbox, and do not
change the saved policies.

## How a reply is built

A reply is a short loop of model rounds. A round either asks for up to four
read-only checks or offers the final answer or plan. Extra checks are refused
and the model is told so. Each round's checks are saved on the working message,
so the panel shows what is being checked while the reply is still running. A
check that fails, such as an incomplete date range, comes back to the model as
a fact. It does not end the turn. The seventh round may not ask for checks. It
answers from what was found instead of failing.

A plan the server refuses, such as an unknown slot, a period that is already
published, or a range outside the period, is handed back to the model as a
`plan_check` result. The model gets two chances to correct it before the turn
fails. A clear manager instruction needs no separate justification (D26).
When no reason was supplied, the actual request is recorded as the audit reason;
the agent explains its choices separately. A request for an unnecessary reason
is handed back to the model for correction. Essential missing targets or dates
are clarified with the manager.

Every round resends the conversation, so only the recent part goes in full.
The newest plan is sent whole, which lets "instead use Dana" revise it. So are
the last two turns' check results. Older plans become summaries (kind, dates,
reasons, counts), and older checks list only the tool names. The snapshot hash
and the generated slot grid never reach the model. Replies may use `-`/`1.`
lists and **bold**. The panel renders these as elements, never as HTML.

## Approval and persistence

Sending a message never changes scheduling or profile data. It starts a
background reply and the browser polls the saved conversation, so long model
requests do not hold a browser request open. While a reply runs the poll asks
only for the working message onward (`?from_message=`): nothing before it can
change until it finishes, and the whole thread with every earlier plan grew
with the conversation. Stop discards any late response;
it does not interrupt an HTTP completion already running at the provider.

The Apply button approves the server-stored plan. The server checks its owner
and a snapshot of the profile, availability, preferences and target schedule.
For a new period it also checks the existing period list. Stale plans must be
recreated. A new message supersedes the previous pending plan. Repeated Apply
requests return the original receipt without duplicating changes.

All approved domain writes, availability updates, history and the receipt share
one PostgreSQL transaction. A later failure rolls back earlier writes. Applying
a schedule plan refreshes the board and navigates to the affected week.

The current manager login uses one team password, rather than individual
manager accounts. Conversation ownership therefore uses a separate signed
HttpOnly browser identity, scoped to the team, that survives logout. Histories
are separate across browsers and teams; managers sharing a browser also share
its history. Cookies expire after one year, and deleting cookies or changing
the session signing secret loses access to that browser's history. Cross-device
manager history would require individual manager accounts.

The conversation supports one plan kind per approval. A request to add an
employee and then schedule a week proceeds in two approvals. Ordinary changes
have the existing 40-operation ceiling; generation previews can cover up to
63 days. Existing published schedules must return to draft before editing.
The existing autonomous copilot console remains available under the drawer's
Overview tab. Invisible automatic briefings are disabled for this surface.

## Code and verification

`backend/src/app/bl/manager_chat.py` orchestrates the conversation and calls
the existing tools and services. `backend/src/app/dal/repository/chat.py` owns
the private transcripts, turn idempotency and approval transaction.
`frontend/src/components/Management/AgentChat.tsx` renders the conversation;
`useManagerChat.ts` manages history, polling and explicit approval requests.

Routes live under `/api/agent/chats`: list/create, read/delete by chat id,
send messages, stop, and apply/dismiss a stored message plan. They all require
the existing boss role plus the signed conversation identity. Employee and
member sessions cannot use them. The new tables are created by the existing
idempotent startup schema initialization.

Run the ordinary backend suite with `python -m pytest`. Optional real database
checks in `tests/test_manager_chat_postgres.py` require `CHAT_TEST_DSN` pointing
to a disposable PostgreSQL database. Each test creates and drops its own schema.
Frontend checks are `npx tsc --noEmit`, `npm run lint` and `npm run build`.

## Agreed product target — 2026-10-06

This section records the manager's design decisions from the grill-me interview.
It describes requested behavior and proposed implementation work, not features
already delivered. The sections above describe the current implementation.

### Primary workflow and screen

The primary workflow is managing an existing schedule and the team: absences,
replacements, recurring availability, departures, shift definitions and questions.
The chat and board remain visible together on desktop, with more space given to
the chat. Manual employee, constraint and schedule controls remain available.
The existing day/week focus must stay explicit. Manual edits update the shared
state and invalidate proposals whose underlying facts changed.

### Conversation decisions

- **Ask for essential missing information once.** For sickness with no known
  date range, ask which dates the employee is unavailable. Reuse a range already
  established in the conversation. For university availability, ask for missing
  weekdays and hours together; never infer an all-week restriction from the
  word "university". New shift staffing and role requirements must be reused
  when unambiguous or clarified when their mapping is unknown.
- **The manager chooses replacements.** Present checked eligible candidates
  with short explanations, then prepare the complete plan after the manager
  selects. An explicitly named replacement goes directly to validation and
  proposal. Candidate selection and answers to clarification questions are
  distinct from approval of a prepared plan.
- **No unsolicited rule exceptions.** If nobody fits, explain the uncovered
  shift and offer compliant alternatives or ask for guidance. Do not propose
  a conflicting replacement as the recommended next action. A separately
  requested exception must still name its consequences and receive explicit
  exception approval; ordinary "yes" does not approve it.
- **Approve by button or explicit conversation reply.** "כן, תעשה" can apply
  the most recent displayed proposal. "כן" in response to a question continues
  planning. Approval must identify the displayed proposal revision, check its
  ownership and current snapshot, and use the existing atomic apply path.
  Ambiguous, stale, superseded or already dismissed proposals cannot be applied.
  Retries return the original receipt rather than performing the writes twice.
- **Revisions preserve the rest of the proposal.** "במקום דנה שים את יוסי"
  revises the existing proposal without dropping other changes or absence
  constraints. A proposed change is never treated as an already saved fact.

### Required scenarios

| Manager request | Required behavior |
|---|---|
| "תשבץ לי את יום שני כמו שבוע שעבר" | Copy the same employees into the same shifts on the target Monday. Check current rules and availability. Explain conflicts and present replacement candidates for selection. Ask when the source date or shift mapping cannot be resolved. |
| "תוסיף אילוץ קבוע, נדב באוניברסיטה" | Resolve the recurring weekdays and hours, then propose a visible, editable recurring constraint while preserving Nadav's other details. |
| "תמחק את הילה, היא חולה ותמצא לה מחליף" | Resolve the absence range, inspect every affected assignment, present candidates, and prepare one plan containing the absence and the selected removals/replacements. Include unavailable dates on which no shift exists. |
| "תמחק את עודד, הוא התפטר" | End active membership and remove affected future assignments in one proposal, preserving past history. Show resulting gaps before approval; offer replacement work afterward. Resolve an essential unknown departure date. |
| "מי עבד הכי הרבה בסופ״ש" | Compute the requested period's workload using tools. Proposed display: scheduled hours and shift count together. Describe the data as scheduled work; it does not establish attendance. Use the team's weekend definition or clarify an unknown one. |
| "מי יכול לתפוס משמרת ברביעי" | Resolve the date and target shift from context or clarify them. Present checked candidates and their relevant availability, qualification and workload trade-offs. Selecting a candidate prepares a proposal. |
| "תשבץ את היום" | Consider every shift that runs on the requested date and its staffing/role requirements. Every gap remains visible; a morning-only result cannot be presented as a fully staffed day. |
| "תשנה את המשמרות ל־12–00, 00–12" | Preview 12:00–00:00 and 00:00–12:00 definitions, the affected current draft and future construction. Propose rebuilding the affected draft under the new structure, retaining existing employees where suitable and checking the new hours. Approve the definitions and revised draft together. |

### Full-day scheduling: first priority

The reported defect is a request for a whole day resulting in only the morning
being staffed. Its root cause has not yet been reproduced. The existing slot
builder enumerates declared shifts that run on each requested date; there is no
fixed morning-only slot builder. Investigation must capture the actual profile,
stored grid, selected day, planner response, scheduler response and audited
preview for a failing example.

Coverage must be computed using the shared staffing arithmetic, including
headcount, required roles and whether a trainee counts toward staffing. A
prepared result must account for every requested slot: staffed, partially staffed
or unstaffed. The reply and preview must use the computed result rather than
trust a model's "day completed" summary. Explain known shortages and say when
a cause is unknown instead of inventing a reason. Candidate availability alone
does not prove a complete feasible solution across all shifts.

Use the existing bounded repair behavior when appropriate; do not introduce an
unbounded loop or claim that a retry guarantees coverage. The full-period
`Scheduler.generate` and the verified `generate_span` currently use different
paths, so reproduce and verify the defect on both relevant entry points.

### Verified implementation gaps

- `profile_service.validation.keep_existing_names` rejects removal of employee
  and shift names. Departures and replacement of a shift vocabulary need explicit
  lifecycle/migration operations, rather than dropping the identity guard on
  every profile edit.
- `CHAT_SCHEMA`, `ChatPlan` and `ManagerChatService.apply` support one plan kind
  at a time. Retirement and shift restructuring require a profile change plus
  schedule changes in the same approval transaction.
- Existing generation retains saved slot definitions. `_prepare_generation`
  refuses assignments with new shift names outside the saved grid, while
  `_commit_generation` replaces slots only for a newly created period. Updating
  the profile alone cannot migrate an existing draft to the new shift structure.
- `start_chat_turn` supersedes pending proposals when any message is sent.
  Conversational approval must resolve its target before that transition; it
  cannot be implemented just by telling the model that "yes" means Apply.
- The prompt currently allows proposing rule exceptions without an explicit
  current request. Replacement recommendations need the agreed compliant-only
  default across prompt, tool results and proposal validation.
- Conversation context currently carries the latest 32 messages, with selective
  summaries of older plans/checks. Long-running tasks need explicit unresolved
  details and selected candidates if they would otherwise fall out of that window.

### Implementation order and maintenance

1. **Reproduce and fix full-day coverage.** Add meaningful multi-shift regression
   cases and make the reply/card show actual completion and gaps. Preserve other
   dates and honor an explicitly requested morning-only scope.
2. **Stabilize selection and approval.** Separate clarification, candidate
   selection, proposal revision and approval using the existing stored message
   statuses. Share the same apply function between text and button approval.
3. **Add two concrete compound operations.** Retirement updates membership and
   future assignments; shift restructuring updates definitions, the affected
   draft grid and proposed assignments. Preview in memory and commit the profile,
   schedule, audit log and receipt together. Reuse the current services and
   transaction boundary; a general workflow engine is unnecessary.
4. **Deliver the chat-led split view.** Reuse `AgentChat`, the board and existing
   design tokens. Add useful candidate and per-shift coverage displays. Preserve
   Hebrew RTL, keyboard interaction and a workable narrow-screen layout.
5. **Refactor around the delivered responsibilities.** Keep chat orchestration
   readable by extracting context assembly and concrete plan preparation/apply
   only where they have become separate responsibilities. Retain shared audit,
   slot-building and profile validation. Avoid a second scheduler or tool system.

Implementation proposals: represent departure with an effective inactive date;
retain historical shift definitions/times for historical calculations; map
eligibility and shift-specific recurring constraints explicitly when changing
shift identities. Do not infer qualification for a new shift name. The migration
preview must include affected manual placements and uncovered roles, so preserving
a stale pin cannot conceal an invalid new assignment.

The agreed migration scope is the affected current draft plus future construction.
Previously published periods require an explicit return-to-draft step before
editing. An operation blocked by a published affected period must explain that
block rather than report completion. Effective dates, unknown staffing and
ambiguous old-to-new qualification mappings are runtime clarifications when
needed; they are not defaults to guess during implementation.

### Acceptance checks

- A day with morning, evening and night includes every required slot in the
  preview. A deliberately partial model answer cannot produce a "fully staffed"
  reply. A genuine shortage remains visible without a conflicting recommendation.
- Filling a day preserves valid existing placements; rebuilding touches only
  the requested dates. A specific morning-only request remains morning-only.
- Copying last Monday translates dates, preserves employee/shift choices and
  checks current constraints. An unavailable employee produces candidate selection.
- After the manager supplies absence dates, the agent retains them through
  candidate selection and revisions; it does not ask for the same dates again.
- No eligible candidate results in a gap and a request for guidance. An ineligible
  option is not offered as a compliant replacement.
- Text and button approval have the same receipt, transaction, ownership,
  idempotency and stale-state behavior. "Yes" to a clarification saves nothing.
- Retirement keeps history, removes the relevant future placements and exposes
  all resulting gaps without requiring that replacements already be selected.
- Changing three shifts to two 12-hour shifts previews both profile and grid;
  hours crossing midnight, rest, eligibility and recurring constraints are checked.
  Failure during commit rolls back both the profile and schedule changes.
- A manual change between preview and approval forces a refreshed proposal.
  Cancelling a revision never leaves partially committed domain changes.

### Further improvements proposed

- Keep the current proposal and its revision easy to find beside the composer.
- Show computed coverage per shift and actual checked candidate explanations.
- Show an approval receipt linking to the affected day/week and change history.
- Remember operational preferences only when explicitly requested, with visible
  editing and deletion; a preference never substitutes for a qualification.
- Measure missing-slot rate, repeated clarification questions, failed approvals,
  latency and model/tool rounds without logging credentials or unnecessary private
  conversation content. Use the real requests above as a dialogue regression set.
- Consider streaming replies after correctness and proposal handling are stable;
  retain the current saved-progress mechanism until a measured need warrants it.
