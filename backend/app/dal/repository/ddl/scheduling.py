"""Periods, slots, assignments, constraints and the append-only change log."""

SCHEDULING_DDL = """-- ---------------------------------------------------------------------------
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
    requires_shift_manager BOOLEAN NOT NULL DEFAULT FALSE,
    is_on_call BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (schedule_id, shift_name, slot_date)
);

COMMIT;

ALTER TABLE shift_slots
    ADD COLUMN IF NOT EXISTS required_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS requires_shift_manager BOOLEAN NOT NULL DEFAULT FALSE;

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

"""
