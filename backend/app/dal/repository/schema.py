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
    is_on_call BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (schedule_id, shift_name, slot_date)
);

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
"""
