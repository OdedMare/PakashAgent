"""Agent preferences (D21), the durable job queue (D23) and kept translations (D32)."""

AGENT_DDL = """-- What this workplace has taught the agent, beyond the one-off decisions.
--
-- Unit setup collects rules; this collects the *operational
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
-- Durable jobs: work survives browser and process restarts. The copilot
-- that named the table is gone; its inbox, permission and audit tables are
-- no longer created, and any left in an existing database are unused.
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

-- What code made of a standing source: a rule, a policy, an employee's note,
-- a preference (D32). A *derivative* of the manager's sentence, never a
-- replacement for it -- the sentence stays where it is, and the row is
-- looked up by what the sentence says, so editing it simply stops matching.
--
-- Keyed on the words (`source_key`), the roster and shift names they were
-- checked against (`vocab_key`) and the compiler that read them, because
-- each can change what the words mean for code. `status` 'unresolved' is a
-- kept *negative*: code cannot honour this, so a build need not pay to
-- learn that again. `translation` holds the availability rows, pins and
-- structured requests, with dates only when the sentence named its time.
CREATE TABLE IF NOT EXISTS compiled_sources (
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL,
    vocab_key TEXT NOT NULL,
    compiler TEXT NOT NULL,
    kind TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    binding BOOLEAN NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('compiled','unresolved')),
    translation JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT NOT NULL DEFAULT '',
    -- The last date a fully dated source speaks about; NULL when recurring.
    expires_on DATE,
    -- What the model would ask the manager ("לחסום גם את 23.10?").
    question TEXT NOT NULL DEFAULT '',
    -- What compiling it cost, so a build loading it can say what it saved.
    tokens INTEGER NOT NULL DEFAULT 0,
    anchored_on DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, source_key, vocab_key, compiler)
);

COMMIT;

-- The day a standing sentence was first seen. "חולה 3 ימים" counts from
-- here, and it does not move when the sentence is compiled again for a new
-- roster or prompt -- only new words get a new day.
CREATE TABLE IF NOT EXISTS source_anchors (
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL,
    anchored_on DATE NOT NULL,
    PRIMARY KEY (team_id, source_key)
);

COMMIT;
"""
