"""Panel saves carried between replicas through PostgreSQL (D39).

The store's JSON file reaches every process that mounts the same disk --
the API and `app.worker` in compose. Replicas in a cluster rarely share one,
so a save made on one pod would otherwise apply on that pod alone. Every
save is therefore also written to the database, and every process polls it
on the store's own reload cadence.

The database connection itself is the exception: it is what the poll is
made over, so it stays in the file and the environment.
"""

import json
import logging
from typing import Optional

_KEY = "runtime_settings"
_LOCAL_ONLY_PREFIX = "database_"

_log = logging.getLogger("pakash.settings")


class SharedSettings:
    """The database side of `RuntimeSettingsStore`.

    `shared` is anything with `deployment_value` and
    `write_deployment_value` -- the repository, in production. `seed` is a
    file saved before this existed: written once if the database holds no
    save yet, so an upgraded deployment keeps what its panel already says.
    Nothing here runs before the first poll, so constructing it never
    touches the database.
    """

    def __init__(self, shared, seed: Optional[dict] = None):
        self._shared = shared
        self._seed = seed
        self._version = None

    def pull(self) -> Optional[dict]:
        """A save made elsewhere, as a patch; None when nothing changed.

        A database that does not answer is no change: the settings already
        held stay live, and the next poll asks again.
        """
        try:
            row = self._shared.deployment_value(_KEY)
        except Exception as exc:
            _log.debug("shared settings unreadable: %s", exc)
            return None
        if row is None and self._seed is not None and self.push(self._seed):
            self._seed = None
        if row is not None:
            self._seed = None
        if row is None or row[0] == self._version:
            return None
        self._version = row[0]
        try:
            return json.loads(row[1])
        except ValueError:
            return None

    def push(self, settings: dict) -> bool:
        """Publish a save to every other process.

        Not raised on failure: the save already applies here and is in the
        file, and a database that refuses the write is the thing the panel
        may be in the middle of fixing.
        """
        try:
            self._version = self._shared.write_deployment_value(
                _KEY, json.dumps(shareable(settings), ensure_ascii=False),
            )
        except Exception as exc:
            _log.warning("settings saved locally but not shared: %s", exc)
            return False
        return True


def shareable(settings: dict) -> dict:
    """Everything but the connection to the database that carries it."""
    return {
        key: value for key, value in settings.items()
        if not key.startswith(_LOCAL_ONLY_PREFIX)
    }
