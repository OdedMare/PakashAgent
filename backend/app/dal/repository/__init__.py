"""The only SQL owner in the codebase."""

from app.dal.database.postgres import connect, ensure_schema
from app.dal.repository.interviews import InterviewRepository
from app.dal.repository.schema import SCHEMA


class Repository(InterviewRepository):
    """One repository object composed of the per-concern mixins.

    Callers get a single dependency; each concern still owns its own module.
    """

    def initialize(self) -> None:
        ensure_schema(self._store)
        with connect(self._store) as connection:
            connection.execute(SCHEMA)
            connection.commit()


__all__ = ["Repository", "InterviewRepository", "SCHEMA"]
