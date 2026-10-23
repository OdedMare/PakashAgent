"""Failed password attempts, shared by every process (`common/throttle.py`).

One row per account. A failure opens a window or counts inside the open
one; the limit-th failure locks the account and resets the count. Expired
rows are swept when a success clears its own, so the table stays as small
as the number of accounts being guessed at right now.
"""

from app.dal.database import connect
from app.dal.repository.base import RepositoryBase

THROTTLE_DDL = """
CREATE TABLE IF NOT EXISTS login_attempts (
    account TEXT PRIMARY KEY,
    failures INTEGER NOT NULL DEFAULT 0,
    window_ends TIMESTAMPTZ NOT NULL,
    locked_until TIMESTAMPTZ
);

COMMIT;
"""

_FAIL = """
INSERT INTO login_attempts AS attempt (account, failures, window_ends)
VALUES (%(account)s, 1, NOW() + make_interval(secs => %(window)s))
ON CONFLICT (account) DO UPDATE SET
    failures = CASE WHEN attempt.window_ends > NOW() THEN attempt.failures + 1 ELSE 1 END,
    window_ends = CASE WHEN attempt.window_ends > NOW() THEN attempt.window_ends
                       ELSE EXCLUDED.window_ends END
RETURNING failures
"""

_LOCK = """
UPDATE login_attempts
SET failures = 0, locked_until = NOW() + make_interval(secs => %(lockout)s)
WHERE account = %(account)s
"""

_SWEEP = """
DELETE FROM login_attempts
WHERE window_ends < NOW() AND (locked_until IS NULL OR locked_until < NOW())
"""


class ThrottleRepository(RepositoryBase):
    def throttle_locked_for(self, account: str) -> float:
        """Seconds the account stays locked; 0 when it is not."""
        rows = self._all(
            "SELECT EXTRACT(EPOCH FROM locked_until - NOW()) AS remaining "
            "FROM login_attempts WHERE account = %s AND locked_until > NOW()",
            (account,),
        )
        return float(rows[0]["remaining"]) if rows else 0.0

    def throttle_fail(self, account: str, limit: int, window: float, lockout: float) -> None:
        """Count one wrong guess; the `limit`-th inside the window locks."""
        params = {"account": account, "window": float(window), "lockout": float(lockout)}
        with connect(self._store) as connection:
            failures = connection.execute(_FAIL, params).fetchone()["failures"]
            if failures >= limit:
                connection.execute(_LOCK, params)
            connection.commit()

    def throttle_clear(self, account: str) -> None:
        """A right guess: the count starts over, and stale rows go."""
        with connect(self._store) as connection:
            connection.execute(
                "UPDATE login_attempts SET failures = 0 WHERE account = %s", (account,))
            connection.execute(_SWEEP)
            connection.commit()
