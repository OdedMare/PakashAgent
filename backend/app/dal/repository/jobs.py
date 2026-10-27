"""The shared durable queue for chat turns, generation, and translations.

The table is still called `copilot_jobs`: the copilot that named it is gone,
and renaming a live table is a migration for no behaviour.
"""

from contextlib import contextmanager

from psycopg.types.json import Jsonb

from app.common.actor import current_actor
from app.common.errors import NotFoundError
from app.dal.database import bind_job_connection, connect
from app.dal.repository.base import RepositoryBase, new_id


_COMPLETE = "complete"
# How many candidates one claim looks at. Running jobs a live worker holds
# are skipped by their advisory lock, so this only has to exceed how many
# can be running at once; without a bound every poll locked the whole queue,
# and a second worker polling meanwhile skipped all of it and found nothing.
_CLAIM_WINDOW = 50


def enqueue(connection, team_id, key, kind, payload):
    # Whoever queued it acts when it runs: the worker restores this, so a
    # build's change-log rows name the manager who started it.
    if current_actor() and "actor" not in payload:
        payload = dict(payload, actor=current_actor())
    return connection.execute("""
        INSERT INTO copilot_jobs (id, team_id, dedupe_key, kind, payload)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (team_id, dedupe_key) DO NOTHING RETURNING *
    """, (new_id(), team_id, key, kind, Jsonb(payload))).fetchone()


class JobsRepository(RepositoryBase):
    def enqueue_copilot_job(self, team_id, dedupe_key, kind="scan", payload=None):
        with connect(self._store) as connection:
            row = enqueue(connection, team_id, dedupe_key, kind, payload or {})
            connection.commit()
        return dict(row) if row else None

    def queue_generation_job(self, team_id, schedule_id):
        """Resume and enqueue one durable job per unfinished model span."""
        with connect(self._store) as connection:
            row = connection.execute("""
                SELECT generation FROM schedules WHERE id=%s AND team_id=%s FOR UPDATE
            """, (schedule_id, team_id)).fetchone()
            if row is None:
                raise NotFoundError("הסידור לא נמצא")
            if (row["generation"] or {}).get("status") == "complete":
                return
            generation = row["generation"] or {}
            for span in generation.get("days") or []:
                if span.get("status") == _COMPLETE:
                    continue
                first = str(span.get("date") or "")
                through = str(span.get("through") or first)
                key = "generation:%s:%s:%s" % (schedule_id, first, through)
                enqueue(connection, team_id, key, "generation", {
                    "schedule_id": schedule_id,
                    "date": first,
                    "through": through,
                })
                connection.execute("""
                    UPDATE copilot_jobs SET status='queued', attempts=0,
                        run_after=NOW(), finished_at=NULL, error=''
                    WHERE team_id=%s AND dedupe_key=%s
                        AND status IN ('complete','failed')
                """, (team_id, key))
            connection.execute("""
                UPDATE schedules SET generation=COALESCE(generation,'{}'::jsonb)
                    || '{"status":"running","cancel_requested":false,"dismissed":false}'::jsonb,
                    updated_at=NOW()
                WHERE id=%s AND team_id=%s
            """, (schedule_id, team_id))
            connection.execute("""
                UPDATE schedules SET generation=jsonb_set(generation, '{activity}',
                    to_jsonb('הבקשה נשמרה וממתינה להתחלת העבודה…'::text), true)
                WHERE id=%s AND team_id=%s AND EXISTS (
                    SELECT 1 FROM copilot_jobs WHERE team_id=%s
                        AND kind='generation' AND payload->>'schedule_id'=%s
                        AND status='queued')
            """, (schedule_id, team_id, team_id, schedule_id))
            connection.commit()

    @contextmanager
    def claim_copilot_job(self, lane="any"):
        """A session lock outlives commits and releases on worker death.

        Running jobs with no owner are immediately eligible again. A slow
        live worker keeps its lock, regardless of how long its model takes.
        """
        with connect(self._store) as connection:
            job = self._claim_job(connection, lane)
            if job is None:
                yield None
                return
            try:
                with bind_job_connection(self._store, connection):
                    yield job
            finally:
                if not connection.closed:
                    connection.rollback()
                    if job.get("_schedule_lock"):
                        connection.execute(
                            "SELECT pg_advisory_unlock(hashtextextended(current_schema() || %s, 0))",
                            (":schedule:" + job["payload"]["schedule_id"],),
                        )
                    connection.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(current_schema() || %s, 0))",
                        (":job:" + job["id"],),
                    )
                    connection.commit()

    def _claim_job(self, connection, lane="any"):
        lane_sql = {
            "interactive": "AND kind='manager_chat'",
            "background": "AND kind<>'manager_chat'",
            "any": "",
        }.get(lane)
        if lane_sql is None:
            raise ValueError("Unknown worker lane: %s" % lane)
        # Queued before running: a running row is claimable only when its
        # worker died, and live ones would otherwise fill the window first.
        candidates = connection.execute("""
            SELECT id, kind, payload FROM copilot_jobs
            WHERE status IN ('queued','running') AND run_after <= NOW()
            %s
            ORDER BY status='running',
                CASE kind WHEN 'manager_chat' THEN 0 WHEN 'generation' THEN 1 ELSE 2 END,
                run_after, created_at
            LIMIT %d
            FOR UPDATE SKIP LOCKED
        """ % (lane_sql, _CLAIM_WINDOW)).fetchall()
        for candidate in candidates:
            locked = connection.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(current_schema() || %s, 0)) AS locked",
                (":job:" + candidate["id"],),
            ).fetchone()["locked"]
            if not locked:
                continue
            schedule_locked = False
            schedule_id = (candidate.get("payload") or {}).get("schedule_id")
            if candidate["kind"] == "generation" and schedule_id:
                schedule_locked = connection.execute(
                    "SELECT pg_try_advisory_lock(hashtextextended(current_schema() || %s, 0)) AS locked",
                    (":schedule:" + schedule_id,),
                ).fetchone()["locked"]
                if not schedule_locked:
                    connection.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(current_schema() || %s, 0))",
                        (":job:" + candidate["id"],),
                    )
                    continue
            try:
                row = connection.execute("""
                    UPDATE copilot_jobs SET status='running', attempts=attempts+1,
                        started_at=NOW(), error='' WHERE id=%s RETURNING *
                """, (candidate["id"],)).fetchone()
                connection.commit()
                claimed = dict(row)
                claimed["_schedule_lock"] = schedule_locked
                return claimed
            except Exception:
                # Advisory locks are session-scoped, so returning this pooled
                # connection while either is held would strand the job.
                connection.rollback()
                if schedule_locked:
                    connection.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(current_schema() || %s, 0))",
                        (":schedule:" + schedule_id,),
                    )
                connection.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(current_schema() || %s, 0))",
                    (":job:" + candidate["id"],),
                )
                connection.commit()
                raise
        connection.commit()
        return None

    def finish_copilot_job(self, job_id, error="", retry=False):
        self._execute("""
            UPDATE copilot_jobs SET status=%s, error=%s,
                run_after=CASE WHEN %s THEN NOW() + INTERVAL '10 seconds' ELSE run_after END,
                finished_at=CASE WHEN %s THEN NULL ELSE NOW() END
            WHERE id=%s
        """, ("queued" if retry else "failed" if error else "complete",
              error[:2000], retry, retry, job_id))

    def purge_finished_jobs(self, older_than_days=30):
        """Delete finished jobs past `older_than_days`; every chat turn is a
        job, so the table otherwise only grows. A build's progress lives on
        its schedule and a turn's on its message, so nothing reads these."""
        with connect(self._store) as connection:
            deleted = connection.execute("""
                DELETE FROM copilot_jobs
                WHERE status IN ('complete','failed')
                    AND finished_at < NOW() - make_interval(days => %s)
            """, (int(older_than_days),)).rowcount
            connection.commit()
        return deleted

    def generation_activity(self, schedule_id, team_id, activity):
        self._execute("""
            UPDATE schedules SET generation=jsonb_set(
                COALESCE(generation,'{}'::jsonb), '{activity}', to_jsonb(%s::text), true)
            WHERE id=%s AND team_id=%s AND generation->>'status'='running'
        """, (activity, schedule_id, team_id))
