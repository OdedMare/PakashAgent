"""The only SQL owner in the codebase."""

from app.dal.database import connect, require_schema
from app.dal.repository.admin import AdminRepository
from app.dal.repository.identities import IdentityRepository
from app.dal.repository.chat import ChatRepository
from app.dal.repository.compiled_sources import CompiledSourcesRepository
from app.dal.repository.deployment import DeploymentRepository
from app.dal.repository.jobs import JobsRepository
from app.dal.repository.schedules import ScheduleRepository
from app.dal.repository.schema import SCHEMA
from app.dal.repository.teams import TeamRepository
from app.dal.repository.throttle import ThrottleRepository

# Keyed like the job locks (`jobs.py`): per schema, so two deployments
# sharing one database do not wait on each other.
_INITIALIZE_LOCK = "hashtextextended(current_schema() || ':initialize', 0)"


class Repository(
    TeamRepository, ScheduleRepository, IdentityRepository,
    ChatRepository, AdminRepository, JobsRepository,
    CompiledSourcesRepository, ThrottleRepository, DeploymentRepository,
):
    """One repository object composed of the per-concern mixins.

    Callers get a single dependency; each concern still owns its own module.
    """

    def initialize(self) -> None:
        """Create the tables if they are not there yet.

        The schema holding them is NOT created here: it is expected to exist
        already, provisioned by whoever owns the database.

        It is checked first rather than assumed. `connect()` puts the schema
        on the search_path as `pakash, public`, and Postgres does not object
        to a name there that does not resolve — it simply falls through to
        `public`. Without this guard a missing schema is not an error at all:
        every table is silently created in `public` instead, which looks like
        success until someone goes looking for the data in the schema it was
        supposed to be in.

        Run under an advisory lock: replicas starting together would
        otherwise race through the same `CREATE ... IF NOT EXISTS`, and
        Postgres answers the loser of that race with a unique violation
        rather than with "already there". The lock is session-level so it
        holds across the script's own COMMITs.
        """
        require_schema(self._store)
        with connect(self._store) as connection:
            connection.execute("SELECT pg_advisory_lock(%s)" % _INITIALIZE_LOCK)
            try:
                connection.execute(SCHEMA)
                connection.commit()
            finally:
                connection.rollback()
                connection.execute("SELECT pg_advisory_unlock(%s)" % _INITIALIZE_LOCK)
                connection.commit()


__all__ = [
    "Repository", "TeamRepository",
    "ScheduleRepository", "IdentityRepository", "SCHEMA",
]
