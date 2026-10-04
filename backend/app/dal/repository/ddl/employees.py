"""Employee identities, constraint requests and swaps (D14)."""

EMPLOYEE_DDL = """-- ---------------------------------------------------------------------------
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

"""
