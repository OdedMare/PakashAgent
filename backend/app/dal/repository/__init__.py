"""The only SQL owner in the codebase."""

from app.dal.database.postgres import connect, require_schema
from app.dal.repository.identities import IdentityRepository
from app.dal.repository.interviews import InterviewRepository
from app.dal.repository.schedules import ScheduleRepository
from app.dal.repository.schema import SCHEMA
from app.dal.repository.teams import TeamRepository


class Repository(
    InterviewRepository, TeamRepository, ScheduleRepository, IdentityRepository
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
        """
        require_schema(self._store)
        with connect(self._store) as connection:
            connection.execute(SCHEMA)
            connection.commit()


__all__ = [
    "Repository", "InterviewRepository", "TeamRepository",
    "ScheduleRepository", "IdentityRepository", "SCHEMA",
]
