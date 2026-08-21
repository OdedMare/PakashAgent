"""Durable jobs, inbox items, permissions, and append-only copilot history."""

from typing import Any, Dict, List, Optional

from psycopg.types.json import Jsonb

from app.common.errors import AgentError, ConflictError
from app.dal.database.postgres import connect
from app.dal.repository.base import RepositoryBase, new_id

MODES = ("observe", "suggest", "auto")
ACTION_FOLLOW_UP = "follow_up_interview"
ACTION_PROFILE_REVIEW = "profile_review"
ACTION_SCHEDULE_REPAIR = "schedule_repair"
ACTION_TYPES = (
    ACTION_FOLLOW_UP, ACTION_PROFILE_REVIEW, ACTION_SCHEDULE_REPAIR,
)


class CopilotRepository(RepositoryBase):
    def enqueue_copilot_job(
        self, team_id: str, dedupe_key: str, kind: str = "scan",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[dict]:
        job_id = new_id()
        rows = self._all("""
            INSERT INTO copilot_jobs (
                id, team_id, kind, payload, dedupe_key
            ) VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (team_id, dedupe_key) DO NOTHING
            RETURNING *
        """, (job_id, team_id, kind, Jsonb(payload or {}), dedupe_key))
        return rows[0] if rows else None

    def claim_copilot_job(self) -> Optional[dict]:
        """Atomically claim one due job across any number of workers."""
        with connect(self._store) as connection:
            row = connection.execute("""
                WITH next_job AS (
                    SELECT id FROM copilot_jobs
                    WHERE status='queued' AND run_after <= NOW()
                    ORDER BY run_after, created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE copilot_jobs AS job
                SET status='running', attempts=attempts+1,
                    started_at=NOW(), error=''
                FROM next_job
                WHERE job.id=next_job.id
                RETURNING job.*
            """).fetchone()
            connection.commit()
        return dict(row) if row else None

    def finish_copilot_job(
        self, job_id: str, error: str = "", retry: bool = False
    ) -> None:
        if retry:
            self._execute("""
                UPDATE copilot_jobs
                SET status='queued', run_after=NOW() + INTERVAL '1 minute',
                    error=%s
                WHERE id=%s
            """, (error[:2000], job_id))
            return
        self._execute("""
            UPDATE copilot_jobs
            SET status=%s, finished_at=NOW(), error=%s
            WHERE id=%s
        """, ("failed" if error else "complete", error[:2000], job_id))

    def recover_copilot_jobs(self) -> None:
        """Return work abandoned by a dead process to the queue."""
        self._execute("""
            UPDATE copilot_jobs
            SET status='queued', run_after=NOW(),
                error='worker stopped before completion'
            WHERE status='running'
              AND started_at < NOW() - INTERVAL '10 minutes'
        """)

    def create_copilot_item(
        self, team_id: str, fingerprint: str, kind: str,
        action_type: str, title: str, detail: str = "",
        payload: Optional[Dict[str, Any]] = None,
        source_job_id: Optional[str] = None,
    ) -> Optional[dict]:
        item_id = new_id()
        rows = self._all("""
            INSERT INTO copilot_items (
                id, team_id, source_job_id, fingerprint, kind, action_type,
                title, detail, payload
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (team_id, fingerprint) DO NOTHING
            RETURNING *
        """, (item_id, team_id, source_job_id, fingerprint, kind,
              action_type, title, detail, Jsonb(payload or {})))
        if not rows:
            return None
        item = rows[0]
        self.append_copilot_audit(
            team_id, "created", item_id=item["id"],
            after_state={"status": item["status"], "kind": item["kind"]},
            message=title,
        )
        return item

    def copilot_item(self, item_id: str, team_id: str) -> dict:
        return self._one(
            "SELECT * FROM copilot_items WHERE id=%s AND team_id=%s",
            (item_id, team_id),
        )

    def copilot_items(
        self, team_id: str, status: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        query = "SELECT * FROM copilot_items WHERE team_id=%s"
        params: List[object] = [team_id]
        if status:
            query += " AND status=%s"
            params.append(status)
        query += " ORDER BY created_at DESC, id LIMIT %s"
        params.append(int(limit))
        return self._all(query, tuple(params))

    def transition_copilot_item(
        self, item_id: str, team_id: str, status: str,
        before_state: Optional[dict] = None,
        after_state: Optional[dict] = None,
        verification: Optional[dict] = None,
        actor: str = "manager",
    ) -> dict:
        current = self.copilot_item(item_id, team_id)
        self._execute("""
            UPDATE copilot_items
            SET status=%s, before_state=%s, after_state=%s, verification=%s,
                updated_at=NOW()
            WHERE id=%s AND team_id=%s
        """, (status,
              Jsonb(before_state) if before_state is not None else None,
              Jsonb(after_state) if after_state is not None else None,
              Jsonb(verification) if verification is not None else None,
              item_id, team_id))
        updated = self.copilot_item(item_id, team_id)
        self.append_copilot_audit(
            team_id, status, item_id=item_id, actor=actor,
            before_state={"status": current["status"], **(before_state or {})},
            after_state={"status": status, **(after_state or {})},
            verification=verification,
        )
        return updated

    def copilot_permissions(self, team_id: str) -> List[dict]:
        stored = {
            row["action_type"]: row for row in self._all(
                "SELECT * FROM copilot_permissions WHERE team_id=%s",
                (team_id,),
            )
        }
        return [stored.get(action_type) or {
            "team_id": team_id, "action_type": action_type,
            "mode": "suggest", "updated_at": None,
        } for action_type in ACTION_TYPES]

    def copilot_permission(self, team_id: str, action_type: str) -> str:
        for row in self.copilot_permissions(team_id):
            if row["action_type"] == action_type:
                return row["mode"]
        return "suggest"

    def set_copilot_permission(
        self, team_id: str, action_type: str, mode: str
    ) -> dict:
        if action_type not in ACTION_TYPES:
            raise AgentError("סוג פעולת קופיילוט אינו מוכר")
        if mode not in MODES:
            raise AgentError("רמת הרשאה אינה תקינה")
        before = self.copilot_permission(team_id, action_type)
        self._execute("""
            INSERT INTO copilot_permissions (team_id, action_type, mode)
            VALUES (%s,%s,%s)
            ON CONFLICT (team_id, action_type)
            DO UPDATE SET mode=EXCLUDED.mode, updated_at=NOW()
        """, (team_id, action_type, mode))
        row = self._one("""
            SELECT * FROM copilot_permissions
            WHERE team_id=%s AND action_type=%s
        """, (team_id, action_type))
        self.append_copilot_audit(
            team_id, "permission_changed", actor="manager",
            before_state={"action_type": action_type, "mode": before},
            after_state={"action_type": action_type, "mode": mode},
        )
        return row

    def append_copilot_audit(
        self, team_id: str, event: str, item_id: Optional[str] = None,
        actor: str = "system", before_state: Optional[dict] = None,
        after_state: Optional[dict] = None,
        verification: Optional[dict] = None, message: str = "",
    ) -> dict:
        row_id = new_id()
        self._execute("""
            INSERT INTO copilot_audit (
                id, team_id, item_id, event, actor, before_state,
                after_state, verification, message
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (row_id, team_id, item_id, event, actor,
              Jsonb(before_state) if before_state is not None else None,
              Jsonb(after_state) if after_state is not None else None,
              Jsonb(verification) if verification is not None else None,
              message))
        return self._one(
            "SELECT * FROM copilot_audit WHERE id=%s AND team_id=%s",
            (row_id, team_id),
        )

    def copilot_audit(self, team_id: str, limit: int = 100) -> List[dict]:
        return self._all("""
            SELECT * FROM copilot_audit
            WHERE team_id=%s ORDER BY created_at DESC, id LIMIT %s
        """, (team_id, int(limit)))

    def latest_profile_updated_at(self, team_id: str):
        rows = self._all("""
            SELECT updated_at FROM interview_sessions
            WHERE team_id=%s AND status='complete' AND profile IS NOT NULL
            ORDER BY updated_at DESC LIMIT 1
        """, (team_id,))
        return rows[0]["updated_at"] if rows else None

    def discard_follow_up(self, session_id: str, team_id: str) -> None:
        """Delete an untouched follow-up session; answered ones are history."""
        with connect(self._store) as connection:
            row = connection.execute("""
                SELECT status, EXISTS (
                    SELECT 1 FROM interview_turns
                    WHERE session_id=%s AND role='user'
                ) AS answered
                FROM interview_sessions WHERE id=%s AND team_id=%s
                FOR UPDATE
            """, (session_id, session_id, team_id)).fetchone()
            if not row or row["status"] != "active" or row["answered"]:
                raise ConflictError(
                    "לא ניתן לבטל ראיון המשך שכבר נענה או הושלם"
                )
            connection.execute(
                "DELETE FROM interview_sessions WHERE id=%s AND team_id=%s",
                (session_id, team_id),
            )
            connection.commit()


__all__ = [
    "CopilotRepository", "MODES", "ACTION_TYPES", "ACTION_FOLLOW_UP",
    "ACTION_PROFILE_REVIEW", "ACTION_SCHEDULE_REPAIR",
]
