"""Database definition applied during repository initialization.

The tables the intro interview needs, plus `teams` — the workspace every
other row hangs off — plus the scheduling half: `schedules`, `shift_slots`,
`assignments`, `availability`, and the append-only `change_log`. Each of
those carries `team_id` from the day it is created, because retrofitting a
tenant key onto a populated table is the expensive version of this.

The scheduling tables encode two decisions directly. `assignments.reason`
exists because every assignment carries the agent's reasoning (D8), and
`change_log` is append-only because it is the only history the system keeps
(D4) — there are no version rows and no rollback.

The COMMIT after each independent block is the AiSummryIO convention and is
load-bearing: the whole script is sent as one simple-query message, which
Postgres implicitly wraps in a single transaction unless the text commits
along the way. Without the checkpoints, one guarded migration failing on a
particular database's data rolls back every unrelated statement that already
succeeded in the same call. Add a new guarded migration after its own COMMIT.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    -- The boss's password, hashed. Never the password itself: this column
    -- ends up in backups, logs of failed migrations, and psql sessions.
    password_hash TEXT NOT NULL,
    -- The unguessable half of the member's share link. Members have no
    -- account by design (D5 -- they only read), so possession of this token
    -- IS their credential, which is why it is generated from `secrets` and
    -- is rotatable without touching the boss's password.
    member_token TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

CREATE TABLE IF NOT EXISTS interview_sessions (
    id TEXT PRIMARY KEY,
    team_id TEXT REFERENCES teams(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','complete')),
    -- The confirmed workplace profile, written once the model returns
    -- status=complete and the boss has approved the summary. NULL until then.
    profile JSONB,
    -- The last question served, so a browser refresh can resume the interview
    -- at the turn it left off without replaying the model.
    pending JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

CREATE TABLE IF NOT EXISTS interview_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL
        REFERENCES interview_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('assistant','user')),
    content TEXT NOT NULL,
    -- The question payload the assistant turn carried (options, the
    -- recommendation, the topic id). NULL on user turns. Kept so the UI can
    -- re-render a past turn's answer buttons exactly as they were offered,
    -- rather than reconstructing them from prose.
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

CREATE INDEX IF NOT EXISTS interview_turns_session_idx
    ON interview_turns (session_id, created_at);

COMMIT;

-- Guarded migration: `CREATE TABLE IF NOT EXISTS` above is a no-op against a
-- database that predates workspaces, so the new column has to be added
-- separately or it silently never appears on an existing install.
ALTER TABLE interview_sessions
    ADD COLUMN IF NOT EXISTS team_id TEXT REFERENCES teams(id) ON DELETE CASCADE;

COMMIT;

-- Nullable on purpose. Interviews recorded before workspaces existed have no
-- team to point at, and inventing one for them would be a guess; NULL says
-- "unclaimed" honestly, and `claim_orphan_sessions` is what adopts them into
-- the first team that is created.
CREATE INDEX IF NOT EXISTS interview_sessions_team_idx
    ON interview_sessions (team_id, created_at);

COMMIT;

-- ---------------------------------------------------------------------------
-- The scheduling half. Every table below carries `team_id` from creation.
-- ---------------------------------------------------------------------------

-- One living schedule per period (D4). Edited in place; there are no version
-- rows, and its history lives entirely in `change_log`.
CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    -- The period this schedule covers, inclusive. A manager works in weeks
    -- or months; the dates are what the calendar renders and what the audit
    -- groups by, so they are columns rather than a free-text label.
    starts_on DATE NOT NULL,
    ends_on DATE NOT NULL,
    -- 'draft' while the manager is still working; 'published' once the team
    -- may see it. Members read only published schedules -- that is what
    -- makes the member view a view of something finished rather than of
    -- whatever state the manager happened to leave the grid in.
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','published')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

CREATE INDEX IF NOT EXISTS schedules_team_idx
    ON schedules (team_id, starts_on DESC);

COMMIT;

-- Persistent progress for daily generation. JSON keeps the job beside the
-- living schedule it builds: the range, instructions and per-day states are
-- one small document, updated after every model call, and disappear with the
-- schedule through the same ownership boundary.
ALTER TABLE schedules
    ADD COLUMN IF NOT EXISTS generation JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMIT;

-- A slot is one shift on one date: the thing a person is assigned INTO.
-- Kept as rows rather than derived from the profile's shift vocabulary on
-- read, because a schedule must stay readable exactly as it was built even
-- after the manager re-runs the interview and changes the vocabulary under
-- it.
CREATE TABLE IF NOT EXISTS shift_slots (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    schedule_id TEXT NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    -- The workplace's own shift name (D9). Never an enum: the vocabulary is
    -- per-workplace data collected in the interview.
    shift_name TEXT NOT NULL,
    slot_date DATE NOT NULL,
    start_time TEXT NOT NULL DEFAULT '',
    end_time TEXT NOT NULL DEFAULT '',
    -- How many people this slot needs, copied from the vocabulary at build
    -- time so the audit's arithmetic does not shift under a saved schedule.
    headcount INTEGER NOT NULL DEFAULT 1,
    required_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_on_call BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (schedule_id, shift_name, slot_date)
);

COMMIT;

ALTER TABLE shift_slots
    ADD COLUMN IF NOT EXISTS required_roles JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMIT;

CREATE INDEX IF NOT EXISTS shift_slots_schedule_idx
    ON shift_slots (schedule_id, slot_date);

COMMIT;

-- person -> slot, with the agent's reason. The reason is not decoration: it
-- is shown to the manager at confirmation time and is the mechanism by which
-- a bad call is caught while it is still cheap (D8). An assignment written
-- without one defeats the decision, which is why the column is NOT NULL.
CREATE TABLE IF NOT EXISTS assignments (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    schedule_id TEXT NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    slot_id TEXT NOT NULL REFERENCES shift_slots(id) ON DELETE CASCADE,
    -- The employee's name as the interview recorded it. There is no
    -- employees table yet and no per-member identity at all (D10), so the
    -- name from the profile is the identifier the whole product uses.
    employee TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (slot_id, employee)
);

COMMIT;

CREATE INDEX IF NOT EXISTS assignments_schedule_idx
    ON assignments (schedule_id);

COMMIT;

-- Known unavailability, plus the positive "can work" the manager sometimes
-- records. `source` says who put it there: the manager, the agent during a
-- conversation, or the employee having told someone out of band. Employees
-- do not write here themselves -- they have no account (D5/D10) -- so the
-- column records provenance, not authorship by the employee.
CREATE TABLE IF NOT EXISTS availability (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    employee TEXT NOT NULL,
    constraint_date DATE NOT NULL,
    -- Empty means the constraint covers the whole day, which is the answer
    -- the interview asks for explicitly ("does a daily constraint rule out
    -- every shift that day?"). `audit.py` reads it the same way.
    shift_name TEXT NOT NULL DEFAULT '',
    available BOOLEAN NOT NULL DEFAULT FALSE,
    -- Optional clock window. With `available=TRUE` it is the only window in
    -- which the employee may work; with FALSE it is the window they cannot
    -- work. Empty bounds preserve the original whole shift/day meaning.
    start_time TEXT NOT NULL DEFAULT '',
    end_time TEXT NOT NULL DEFAULT '',
    -- Soft rows remain visible to the scheduler and audit but do not remove
    -- the employee from a slot's candidate list.
    is_hard BOOLEAN NOT NULL DEFAULT TRUE,
    reason TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manager'
        CHECK (source IN ('manager','agent','employee_reported','interview')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, employee, constraint_date, shift_name)
);

COMMIT;

CREATE INDEX IF NOT EXISTS availability_team_date_idx
    ON availability (team_id, constraint_date);

COMMIT;

-- Guarded migration for availability windows and soft constraints.
ALTER TABLE availability
    ADD COLUMN IF NOT EXISTS start_time TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS end_time TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS is_hard BOOLEAN NOT NULL DEFAULT TRUE;

COMMIT;

-- Append-only (D4). Never UPDATE or DELETE a row here: this is the only
-- history the system has, and it is what makes "why did Yossi get moved"
-- answerable. Both reasons live here -- the manager's `reason` (why the
-- change is happening) and the agent's `agent_reason` (why it chose this
-- replacement) -- because they answer different questions (D8).
CREATE TABLE IF NOT EXISTS change_log (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    schedule_id TEXT REFERENCES schedules(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    employee TEXT NOT NULL DEFAULT '',
    replaced_employee TEXT NOT NULL DEFAULT '',
    slot_date DATE,
    shift_name TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    agent_reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

CREATE INDEX IF NOT EXISTS change_log_team_idx
    ON change_log (team_id, created_at DESC);

COMMIT;

-- ---------------------------------------------------------------------------
-- Employee identity and the one thing an employee may write (D14).
-- ---------------------------------------------------------------------------

-- A claimed name plus a personal passcode. This is what D10 said did not
-- exist and D14 introduced: without it there is no "his hours" to show,
-- because the share link is one bearer token for the whole team and every
-- visitor looks identical.
--
-- The identity is a claim over a NAME from the workplace profile, not a user
-- record. `employee` matches `assignments.employee` and
-- `availability.employee` exactly -- the whole product identifies people by
-- the name the interview recorded, and inventing a separate id here would
-- mean reconciling two identifiers for one person on every read.
CREATE TABLE IF NOT EXISTS employee_identities (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    employee TEXT NOT NULL,
    -- scrypt, same format and same helpers as the boss password. Never the
    -- passcode itself.
    passcode_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ,
    -- One claim per name per team. This is the constraint that makes a claim
    -- meaningful: the second person to try a taken name is refused rather
    -- than silently sharing it.
    UNIQUE (team_id, employee)
);

COMMIT;

-- An employee's constraint submission, awaiting the manager.
--
-- Deliberately NOT a row in `availability`. A pending request must be
-- invisible to `audit.py` (D3 -- the arithmetic may not move because someone
-- asked), and approval is what promotes it into a real constraint with
-- `source='employee_reported'` (D13). Keeping them in separate tables is what
-- makes "pending changes nothing" a property of the schema rather than a
-- filter every reader has to remember.
CREATE TABLE IF NOT EXISTS constraint_requests (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    employee TEXT NOT NULL,
    constraint_date DATE NOT NULL,
    -- Empty means the whole day, read exactly as `availability.shift_name` is.
    shift_name TEXT NOT NULL DEFAULT '',
    -- FALSE is "I cannot work this" -- the common case. TRUE is an offer to
    -- work, which a manager may also want.
    available BOOLEAN NOT NULL DEFAULT FALSE,
    -- The employee's own words. This is the whole point of letting them
    -- submit: "family event", "exam" is context the manager otherwise never
    -- gets in writing.
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','rejected','withdrawn')),
    -- The manager's answer. A rejection without one tells the employee
    -- nothing, which is how a feature like this stops being used.
    decided_reason TEXT NOT NULL DEFAULT '',
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

CREATE INDEX IF NOT EXISTS constraint_requests_team_idx
    ON constraint_requests (team_id, status, created_at DESC);

COMMIT;

-- Guarded migration: what the employee has already been shown.
--
-- Deliberately NOT `last_seen_at`, which moves on every login and so is
-- always "now" by the time the personal area renders -- there would be
-- nothing left to be new. This column advances only when the employee
-- acknowledges what they were shown, which is what makes "what changed for
-- me since I last looked" answerable at all (D16).
--
-- NULL means "has never acknowledged anything". Read as *everything is new*
-- rather than *nothing is*: a person who has never opened the screen has by
-- definition not seen the moves that concern them, and defaulting the other
-- way would silently swallow exactly the first notification that matters.
ALTER TABLE employee_identities
    ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ;

COMMIT;

-- Guarded migration: where an assignment came from (D18).
--
-- The boss may author a schedule as well as generate one (D6), and until now
-- only the generated half existed. A manually placed assignment has no agent
-- judgment behind it, so `reason` alone could not distinguish "the agent
-- decided this" from "the manager put it here" -- both are just prose.
--
-- This is `availability.source` (D13) applied to the other table, and it
-- means the same thing: **where the information came from, not who typed
-- it**. 'agent' is the default so every row that predates this column keeps
-- the meaning it was written with -- everything before D18 was generated.
--
-- `reason` stays NOT NULL. A manual assignment carries the manager's own
-- sentence, or a plain statement that they placed it; D8 is not relaxed,
-- it is answered by a different voice.
ALTER TABLE assignments
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'agent';

COMMIT;

-- An agreed swap between two employees, awaiting the manager.
--
-- The same shape as `constraint_requests` and for the same reason: a request
-- is inert until the manager rules on it. Approval is what performs the
-- OP_SWAP that `bl/changes.py` already knows how to apply, so nothing here
-- writes an assignment and nothing here is visible to `audit.py` while it
-- waits -- D3 and D14 both hold unchanged.
--
-- What this table adds over `constraint_requests` is a *counterparty*. A
-- constraint concerns one person; a swap is an agreement between two, and
-- the second person's consent is a fact worth storing rather than assuming.
-- `counterparty_agreed` is that consent, and a swap reaches the manager's
-- inbox only once it is TRUE -- otherwise the manager rules on an
-- arrangement the other half has not accepted.
--
-- Both sides are named by `assignments.employee` strings, exactly as
-- `employee_identities` is: the product identifies people by the name the
-- interview recorded, and a second identifier would need reconciling on
-- every read.
CREATE TABLE IF NOT EXISTS swap_requests (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    -- The schedule the swap was proposed against. A swap outlives neither a
    -- deleted schedule nor the period it belongs to.
    schedule_id TEXT NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
    -- The person asking, and the shift they are giving away.
    requester TEXT NOT NULL,
    requester_date DATE NOT NULL,
    requester_shift TEXT NOT NULL DEFAULT '',
    -- The person asked, and the shift they give back. Both are required: a
    -- swap is an exchange, and a one-sided handover is a different feature
    -- with different fairness consequences (it moves hours, rather than
    -- trading them) -- not one to smuggle in through the same table.
    counterparty TEXT NOT NULL,
    counterparty_date DATE NOT NULL,
    counterparty_shift TEXT NOT NULL DEFAULT '',
    -- The requester's own words, the same context `constraint_requests`
    -- exists to capture in writing.
    reason TEXT NOT NULL DEFAULT '',
    -- The other half's answer. NULL while they have not replied, which is
    -- distinct from FALSE -- "has not answered" and "said no" are different
    -- states and the requester needs to tell them apart.
    counterparty_agreed BOOLEAN,
    counterparty_replied_at TIMESTAMPTZ,
    -- 'awaiting_counterparty' precedes 'pending': a swap is not the
    -- manager's problem until both employees agree. 'declined' is the
    -- counterparty's refusal, kept separate from the manager's 'rejected'
    -- for the reason `withdrawn` is kept separate from both.
    status TEXT NOT NULL DEFAULT 'awaiting_counterparty'
        CHECK (status IN ('awaiting_counterparty','pending','approved',
                          'rejected','declined','withdrawn')),
    -- The manager's answer, read by both employees.
    decided_reason TEXT NOT NULL DEFAULT '',
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

CREATE INDEX IF NOT EXISTS swap_requests_team_idx
    ON swap_requests (team_id, status, created_at DESC);

COMMIT;

-- Read by the counterparty's inbox, which filters on their name rather than
-- the requester's -- the one query the index above does not serve.
CREATE INDEX IF NOT EXISTS swap_requests_counterparty_idx
    ON swap_requests (team_id, counterparty, status);

COMMIT;

-- What this workplace has taught the agent, beyond the one-off decisions.
--
-- The intro interview collects rules; this collects the *operational
-- preferences* that only surface later -- "always ask יוסי before רון for a
-- weekend", "notifications go out short and without the reason", "מאיה
-- prefers mornings". They are not rules (D1/D2 govern those and they stay
-- the boss's own sentences in the profile) and they are not constraints
-- (`availability` is what the audit counts). They are standing context the
-- agent reads before it proposes.
--
-- **A preference is confirmed, never inferred into existence.** One decision
-- is a decision; it becomes a preference when the manager says it is one.
-- `status` starts at 'suggested' when the agent proposes it from something
-- it noticed, and only the manager's approval moves it to 'active' -- the
-- same shape `constraint_requests` uses, and for the same reason: the row
-- exists so the proposal is visible and editable rather than silently in
-- force. A candidate that is never approved changes nothing.
--
-- **Scoped to one team, like everything else here** (D10). `subject` narrows
-- it further to one employee or one shift when it is about them, empty when
-- it is about the workplace -- which is what makes "מאיה prefers mornings"
-- storable without becoming a claim about everybody.
CREATE TABLE IF NOT EXISTS agent_preferences (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    -- What the preference is about: 'staffing', 'notification', 'employee',
    -- 'shift', or 'general'. Presentation only -- the UI groups on it and
    -- nothing in code branches on it, exactly as `briefing.KIND_*` works.
    kind TEXT NOT NULL DEFAULT 'general',
    -- The employee or shift this is about, empty when it is about the
    -- workplace as a whole.
    subject TEXT NOT NULL DEFAULT '',
    -- The preference in the manager's own words. Natural language, for the
    -- same reason rules are (D2): there is no structured vocabulary to
    -- compile this into and inventing one would be reversing that decision
    -- by the back door.
    text TEXT NOT NULL,
    -- Why it is remembered. For a manager-authored one this is often empty;
    -- for one the agent suggested it is what the agent noticed, which is
    -- what makes the suggestion checkable rather than merely assertive.
    evidence TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('suggested','active','archived')),
    -- Where it came from: 'manager' typed it, 'agent' proposed it from
    -- something it observed. `availability.source` (D13) applied again --
    -- where the information came from, not who typed it.
    source TEXT NOT NULL DEFAULT 'manager',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

CREATE INDEX IF NOT EXISTS agent_preferences_team_idx
    ON agent_preferences (team_id, status, created_at DESC);

COMMIT;

-- ---------------------------------------------------------------------------
-- Durable copilot: work survives browser and process restarts.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS copilot_jobs (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'scan',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    dedupe_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','complete','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    run_after TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, dedupe_key)
);

COMMIT;

CREATE INDEX IF NOT EXISTS copilot_jobs_ready_idx
    ON copilot_jobs (status, run_after, created_at);

COMMIT;

CREATE TABLE IF NOT EXISTS copilot_items (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    source_job_id TEXT REFERENCES copilot_jobs(id) ON DELETE SET NULL,
    fingerprint TEXT NOT NULL,
    kind TEXT NOT NULL
        CHECK (kind IN ('observation','proposal','failure')),
    action_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','dismissed','applied',
                          'failed','rolled_back')),
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    before_state JSONB,
    after_state JSONB,
    verification JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, fingerprint)
);

COMMIT;

CREATE INDEX IF NOT EXISTS copilot_items_team_idx
    ON copilot_items (team_id, status, created_at DESC);

COMMIT;

CREATE TABLE IF NOT EXISTS copilot_permissions (
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'suggest'
        CHECK (mode IN ('observe','suggest','auto')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, action_type)
);

COMMIT;

-- Append-only. Rollback adds another event; it never erases the action that
-- happened, so the record remains honest after recovery.
CREATE TABLE IF NOT EXISTS copilot_audit (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    item_id TEXT REFERENCES copilot_items(id) ON DELETE SET NULL,
    event TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    before_state JSONB,
    after_state JSONB,
    verification JSONB,
    message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

CREATE INDEX IF NOT EXISTS copilot_audit_team_idx
    ON copilot_audit (team_id, created_at DESC);

COMMIT;
"""
