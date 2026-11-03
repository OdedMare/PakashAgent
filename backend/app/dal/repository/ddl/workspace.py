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

"""

# Once per database: whoever had been taken out of the roster (an
# `inactive_from` on or before today, Israel time) comes back to it switched
# off (`on_duty: false`). Reservists come and go, and the on/off switch is
# how a unit now says so; a departure stays available for whoever really
# left. Marked done in `deployment_state`, so a soldier taken out after the
# upgrade is never brought back by a restart. Appended after
# `DEPLOYMENT_DDL`, which creates that table.
ROSTER_SWITCH_DDL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM deployment_state WHERE key = 'migration:roster_switch_off'
    ) THEN
        UPDATE team_profiles AS saved
        SET profile = jsonb_set(saved.profile, '{employees}', (
                SELECT jsonb_agg(
                    CASE WHEN jsonb_typeof(person) = 'object'
                              AND jsonb_typeof(person -> 'inactive_from') = 'string'
                              AND person ->> 'inactive_from' <> ''
                              AND person ->> 'inactive_from'
                                  <= to_char((NOW() AT TIME ZONE 'Asia/Jerusalem')::date, 'YYYY-MM-DD')
                         THEN (person - 'inactive_from') || '{"on_duty": false}'::jsonb
                         ELSE person END
                    ORDER BY position)
                FROM jsonb_array_elements(saved.profile -> 'employees')
                     WITH ORDINALITY AS roster(person, position)
            )),
            revision = saved.revision + 1,
            updated_at = NOW()
        WHERE jsonb_typeof(saved.profile -> 'employees') = 'array'
          AND EXISTS (
              SELECT 1 FROM jsonb_array_elements(saved.profile -> 'employees') AS roster(person)
              WHERE jsonb_typeof(person) = 'object'
                AND jsonb_typeof(person -> 'inactive_from') = 'string'
                AND person ->> 'inactive_from' <> ''
                AND person ->> 'inactive_from'
                    <= to_char((NOW() AT TIME ZONE 'Asia/Jerusalem')::date, 'YYYY-MM-DD'));
        INSERT INTO deployment_state (key, value)
        VALUES ('migration:roster_switch_off', 'done')
        ON CONFLICT (key) DO NOTHING;
    END IF;
END $$;

COMMIT;
"""
