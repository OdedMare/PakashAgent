"""Storage and the approval lock for source-independent change plans."""

from contextlib import contextmanager

from psycopg.errors import SerializationFailure
from psycopg.types.json import Jsonb

from app.common.actor import current_actor
from app.common.errors import ConflictError, NotFoundError
from app.dal.database import atomic
from app.dal.repository.base import RepositoryBase, new_id


class ChangePlanRepository(RepositoryBase):
    def create_change_plan(
        self, team_id: str, body: dict, source: str, source_ref: str = "",
    ) -> dict:
        plan_id = new_id()
        self._execute("""
            INSERT INTO change_plans(
                id,team_id,actor,source,source_ref,body
            ) VALUES (%s,%s,%s,%s,%s,%s)
        """, (plan_id, team_id, current_actor(), source, source_ref, Jsonb(body)))
        return self.get_change_plan(plan_id, team_id)

    def get_change_plan(self, plan_id: str, team_id: str) -> dict:
        return self._one(
            "SELECT * FROM change_plans WHERE id=%s AND team_id=%s",
            (plan_id, team_id),
        )

    @contextmanager
    def change_plan_approval(self, team_id: str, plan_id: str):
        """Lock one pending plan and compose every resulting write atomically."""
        try:
            with atomic(self._store) as connection:
                row = connection.execute("""
                    SELECT * FROM change_plans
                    WHERE id=%s AND team_id=%s FOR UPDATE
                """, (plan_id, team_id)).fetchone()
                if row is None:
                    raise NotFoundError("התוכנית לא נמצאה")
                if row["status"] not in ("pending", "applied"):
                    raise ConflictError("התוכנית כבר אינה ממתינה לאישור")
                yield dict(row)
        except SerializationFailure as exc:
            raise ConflictError(
                "המערכת השתנתה במקביל. יש לרענן ולבקש תוכנית מעודכנת"
            ) from exc

    def mark_change_plan_applied(
        self, plan_id: str, team_id: str, receipt: dict,
    ) -> None:
        self._execute("""
            UPDATE change_plans
               SET status='applied', receipt=%s, applied_at=NOW(), updated_at=NOW()
             WHERE id=%s AND team_id=%s AND status='pending'
        """, (Jsonb(receipt), plan_id, team_id))

    def set_change_plan_status(
        self, plan_id: str, team_id: str, status: str,
    ) -> None:
        if status not in ("dismissed", "superseded", "stale"):
            raise ValueError("unsupported change-plan status")
        self._execute("""
            UPDATE change_plans SET status=%s,updated_at=NOW()
            WHERE id=%s AND team_id=%s AND status='pending'
        """, (status, plan_id, team_id))
