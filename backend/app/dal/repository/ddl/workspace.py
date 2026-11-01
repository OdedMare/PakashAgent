"""Teams and their scheduling profiles."""

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

CREATE TABLE IF NOT EXISTS team_profiles (
    team_id TEXT PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
    profile JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

-- Preserve the latest completed profile when upgrading an installation that
-- used the removed interview flow. Dynamic SQL keeps this migration valid on
-- fresh databases where the legacy table never existed.
DO $$
BEGIN
    IF to_regclass('interview_sessions') IS NOT NULL THEN
        EXECUTE '
            INSERT INTO team_profiles (team_id, profile, created_at, updated_at)
            SELECT DISTINCT ON (team_id) team_id, profile, created_at, updated_at
            FROM interview_sessions
            WHERE team_id IS NOT NULL AND status = ''complete'' AND profile IS NOT NULL
            ORDER BY team_id, updated_at DESC
            ON CONFLICT (team_id) DO NOTHING';
    END IF;
END $$;

COMMIT;

DROP TABLE IF EXISTS interview_turns;
DROP TABLE IF EXISTS interview_sessions;

COMMIT;

-- The operator's controls over a workspace (D28). Guarded, after their own
-- COMMITs, for the same reason as `team_id` above: an existing `teams` table
-- never sees columns added to its CREATE statement.
-- How many employees a team has is its manager's decision, not the
-- operator's, so there is deliberately no seat cap here.
--
-- `active`: FALSE suspends the team. Its data stays; every sign-in and every
-- open session is refused until the operator turns it back on.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;

COMMIT;

-- `notes`: the operator's own remark about the team -- a contact, a unit, a
-- renewal date. Never shown to the team.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS notes TEXT NOT NULL DEFAULT '';

COMMIT;

-- `revision`: bumped on every profile save, and a save may name the revision
-- it was edited from. Two managers editing setup at once otherwise lose
-- whichever save lands first, silently, because a save replaces the whole
-- profile.
ALTER TABLE team_profiles ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 0;

COMMIT;

-- A מכלול (D43): several workplaces joined under one commander. Each linked
-- team stays a team in every respect; this row only names the group and
-- holds the commander's password, hashed like a team's.
CREATE TABLE IF NOT EXISTS complexes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;

-- A team belongs to at most one מכלול. Deleting the מכלול leaves its teams
-- standing, unlinked.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS complex_id TEXT
    REFERENCES complexes(id) ON DELETE SET NULL;

COMMIT;

-- What the commander changed inside a workplace, for that workplace's
-- manager to read (D43). Repeats of one action within a few minutes fold
-- into one row with a count, so a chat turn by turn is one notice.
CREATE TABLE IF NOT EXISTS commander_notices (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    complex_name TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    seen_at TIMESTAMPTZ
);

COMMIT;

CREATE INDEX IF NOT EXISTS commander_notices_unseen
    ON commander_notices (team_id, created_at DESC) WHERE seen_at IS NULL;

COMMIT;

-- A מכלול's duties (תורנויות: מטבח, שמירה…), set by its commander for
-- soldiers of every linked משמרת. `weight` is how many shifts one duty day
-- counts as in the load fairness and statistics read. `days` empty means
-- every day.
CREATE TABLE IF NOT EXISTS complex_duty_types (
    id TEXT PRIMARY KEY,
    complex_id TEXT NOT NULL REFERENCES complexes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    seats INTEGER NOT NULL DEFAULT 1 CHECK (seats >= 1),
    days TEXT[] NOT NULL DEFAULT '{}',
    weight INTEGER NOT NULL DEFAULT 1 CHECK (weight >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (complex_id, name)
);

COMMIT;

-- One soldier on one duty for one whole day. The soldier is named as their
-- own משמרת's roster names them. Owned by the מכלול, not the team: the
-- team's manager sees the row (it blocks the day in their schedule) but its
-- constraint routes never delete it.
CREATE TABLE IF NOT EXISTS complex_duties (
    id TEXT PRIMARY KEY,
    complex_id TEXT NOT NULL REFERENCES complexes(id) ON DELETE CASCADE,
    duty_type_id TEXT NOT NULL REFERENCES complex_duty_types(id) ON DELETE CASCADE,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    employee TEXT NOT NULL,
    duty_date DATE NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, employee, duty_date)
);

COMMIT;

CREATE INDEX IF NOT EXISTS complex_duties_team_date_idx
    ON complex_duties (team_id, duty_date);

COMMIT;

CREATE INDEX IF NOT EXISTS complex_duties_complex_date_idx
    ON complex_duties (complex_id, duty_date);

COMMIT;

"""
