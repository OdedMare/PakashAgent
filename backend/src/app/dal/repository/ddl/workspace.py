"""Teams and the intro interview's tables."""

WORKSPACE_DDL = """
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

-- The operator's controls over a workspace (D28). Guarded, after their own
-- COMMITs, for the same reason as `team_id` above: an existing `teams` table
-- never sees columns added to its CREATE statement.
--
-- `max_employees`: the seat cap the operator sold or granted. NULL means no
-- cap. Enforced where a profile is written (`seats.py`), and only against
-- growth -- lowering it never locks a team out of editing who it has.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS max_employees INTEGER;

COMMIT;

-- `active`: FALSE suspends the team. Its data stays; every sign-in and every
-- open session is refused until the operator turns it back on.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;

COMMIT;

-- `notes`: the operator's own remark about the team -- a contact, a unit, a
-- renewal date. Never shown to the team.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT '';

COMMIT;

"""
