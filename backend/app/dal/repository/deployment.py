"""Values every process of one deployment must agree on (D39).

Two live here: the key that signs session cookies when
`PAKASH_SESSION_SECRET` is not set, and the settings saved in the panel.
Both used to be per process -- a generated key, a local JSON file -- which
is right for one container and wrong for several replicas: each pod signed
with its own key, and a panel save reached only the pod whose disk it
landed on.

`version` grows on every write, so a process polling for a change reads one
small row and compares a number.
"""

from typing import Optional, Tuple

from app.dal.database import connect
from app.dal.repository.base import RepositoryBase

DEPLOYMENT_DDL = """
CREATE TABLE IF NOT EXISTS deployment_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
"""

_CLAIM = """
INSERT INTO deployment_state (key, value) VALUES (%(key)s, %(value)s)
ON CONFLICT (key) DO NOTHING
"""

_WRITE = """
INSERT INTO deployment_state AS state (key, value) VALUES (%(key)s, %(value)s)
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value, version = state.version + 1, updated_at = NOW()
RETURNING version
"""


class DeploymentRepository(RepositoryBase):
    def claim_deployment_value(self, key: str, candidate: str) -> str:
        """The stored value, or `candidate` stored now if there is none.

        Replicas starting together each offer their own candidate; the
        first insert wins and every one of them reads that winner back.
        """
        with connect(self._store) as connection:
            connection.execute(_CLAIM, {"key": key, "value": candidate})
            row = connection.execute(
                "SELECT value FROM deployment_state WHERE key = %s", (key,),
            ).fetchone()
            connection.commit()
        return row["value"]

    def deployment_value(self, key: str) -> Optional[Tuple[int, str]]:
        """`(version, value)`, or None when nothing was ever written."""
        rows = self._all(
            "SELECT version, value FROM deployment_state WHERE key = %s", (key,),
        )
        return (int(rows[0]["version"]), rows[0]["value"]) if rows else None

    def write_deployment_value(self, key: str, value: str) -> int:
        """Store `value` for every process; returns the new version."""
        with connect(self._store) as connection:
            version = connection.execute(
                _WRITE, {"key": key, "value": value},
            ).fetchone()["version"]
            connection.commit()
        return int(version)
