"""Agent preferences (D21) and the durable copilot (D23)."""

AGENT_DDL = """-- What this workplace has taught the agent, beyond the one-off decisions.
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
