"""Shared connection and query primitives for repository modules.

Ported from AiSummryIO. SQL lives in this package and nowhere else — `bl/`
never imports psycopg (backend/app/dal/CLAUDE.md).
"""

import uuid
from typing import List

from app.common.errors import NotFoundError
from app.dal.database import single_statement


def new_id() -> str:
    return str(uuid.uuid4())


class RepositoryBase:
    def __init__(self, settings_store):
        self._store = settings_store

    def health(self) -> dict:
        with single_statement(self._store) as connection:
            connection.execute("SELECT 1").fetchone()
        return {"database": "ok"}

    def _one(self, query: str, params=()) -> dict:
        rows = self._all(query, params)
        if not rows:
            raise NotFoundError("הפריט לא נמצא")
        return rows[0]

    def _all(self, query: str, params=()) -> List[dict]:
        # One statement, so autocommit: no BEGIN/COMMIT round trips
        # (`database.single_statement`). The commit stays for the
        # transaction and job connections, where it is the deferred one.
        with single_statement(self._store) as connection:
            rows = connection.execute(query, params).fetchall()
            connection.commit()
        return [dict(row) for row in rows]

    def _execute(self, query: str, params=()) -> None:
        with single_statement(self._store) as connection:
            connection.execute(query, params)
            connection.commit()

    @staticmethod
    def _touch_schedule(connection, schedule_id: str) -> None:
        connection.execute(
            "UPDATE schedules SET updated_at=NOW() WHERE id=%s", (schedule_id,),
        )
