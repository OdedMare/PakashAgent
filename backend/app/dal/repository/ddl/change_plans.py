"""Persisted, source-independent change plans."""


CHANGE_PLAN_DDL = """
CREATE TABLE IF NOT EXISTS change_plans (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    actor TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    source_ref TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','applied','dismissed','superseded','stale')),
    body JSONB NOT NULL,
    receipt JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at TIMESTAMPTZ
);
COMMIT;

CREATE INDEX IF NOT EXISTS change_plans_team_idx
    ON change_plans(team_id, created_at DESC);
COMMIT;

CREATE UNIQUE INDEX IF NOT EXISTS change_plans_source_ref_idx
    ON change_plans(source, source_ref) WHERE source_ref <> '';
COMMIT;

ALTER TABLE change_log ADD COLUMN IF NOT EXISTS plan_id TEXT
    REFERENCES change_plans(id) ON DELETE SET NULL;
COMMIT;

CREATE INDEX IF NOT EXISTS change_log_plan_idx
    ON change_log(plan_id) WHERE plan_id IS NOT NULL;
COMMIT;
"""
