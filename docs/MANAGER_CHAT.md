# Manager conversation on the shift board

The manager has one saved conversation for questions, recommendations and
management requests. The desktop panel opens alongside the board and can be
resized; mobile uses the existing drawer. New chat and history keep separate
conversations. Enter sends; Shift+Enter adds a line. The existing model provider,
credentials, role routing and FastAPI / business logic / PostgreSQL architecture
remain in use.

## What the agent can do

- Answer schedule and workload questions with the existing read-only tools,
  plus period lookup, change history and a computed workload report for a date range.
- Propose replacements, moves and swaps, including complete sickness plans
  with absence constraints, and show individual replacement selectors.
- Record availability for future dates before a schedule exists.
- Build, fill or rebuild a week as actual assignments shown before approval.
  The manager can revise individual generated assignments. Filling retains all
  saved assignments; rebuilding retains placements made by the manager.
- Add or edit employees, shift definitions, the workplace and initial setup rules.
  Profile patches use the existing profile validation and show before/after values.
- Propose publishing, returning to draft or clearing a period.

The full initial profile, current availability, recurring constraints, rotations,
standing preferences and recent changes accompany the conversation. Arbitrary
written policies are interpreted by the model; supported countable rules are
also checked by the existing deterministic audit. Suggestions prefer compliant
candidates. Exceptions are shown and require a separate checkbox, and do not
change the saved policies.

## Approval and persistence

Sending a message never changes scheduling or profile data. It starts a
background reply and the browser polls the saved conversation, so long model
requests do not hold a browser request open. Stop discards any late response;
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
