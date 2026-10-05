"""Schedule periods and their slot grids."""

from typing import List, Optional

from psycopg.types.json import Jsonb

from app.common.errors import AgentError
from app.common.time_context import israel_today
from app.dal.database.postgres import connect
from app.dal.repository.base import RepositoryBase, new_id


class PeriodRepository(RepositoryBase):
    def create_schedule(self, team_id: str, starts_on: str, ends_on: str) -> dict:
        schedule_id = new_id()
        self._execute("""
            INSERT INTO schedules (id, team_id, starts_on, ends_on)
            VALUES (%s,%s,%s,%s)
        """, (schedule_id, team_id, starts_on, ends_on))
        return self.get_schedule(schedule_id, team_id)

    def get_schedule(self, schedule_id: str, team_id: str) -> dict:
        """A schedule with its slots and assignments, scoped to the team."""
        schedule = self._one(
            "SELECT * FROM schedules WHERE id=%s AND team_id=%s",
            (schedule_id, team_id),
        )
        schedule["slots"] = self.slots(schedule_id, team_id)
        schedule["assignments"] = self.assignments(schedule_id, team_id)
        return schedule

    def list_schedules(self, team_id: str) -> List[dict]:
        """Every period this team has, newest first. Rows only, no slots."""
        return self._all("""
            SELECT id, starts_on, ends_on, status, created_at, updated_at
            FROM schedules WHERE team_id=%s
            ORDER BY starts_on DESC
        """, (team_id,))

    def current_schedule(
        self, team_id: str, published_only: bool = False
    ) -> Optional[dict]:
        """The period in play: the one covering today, else the newest.

        `published_only` is what a member's read passes. A draft is the
        manager's working state -- publishing is the act that makes it theirs.
        """
        clause = " AND status='published'" if published_only else ""
        today = israel_today().isoformat()
        rows = self._all("""
            SELECT id FROM schedules
            WHERE team_id=%s""" + clause + """
            ORDER BY
                (starts_on <= %s AND ends_on >= %s) DESC,
                starts_on DESC
            LIMIT 1
        """, (team_id, today, today))
        if not rows:
            return None
        return self.get_schedule(rows[0]["id"], team_id)

    def set_schedule_status(self, schedule_id: str, team_id: str, status: str) -> dict:
        if status not in ("draft", "published"):
            raise AgentError("סטטוס סידור לא תקין")
        self._execute("""
            UPDATE schedules SET status=%s, updated_at=NOW()
            WHERE id=%s AND team_id=%s
        """, (status, schedule_id, team_id))
        return self.get_schedule(schedule_id, team_id)

    def set_generation(self, schedule_id: str, team_id: str, generation: dict) -> dict:
        """Persist resumable generation progress on the schedule."""
        self._require_schedule(schedule_id, team_id)
        self._execute("""
            UPDATE schedules
               SET generation=%s, updated_at=NOW()
             WHERE id=%s AND team_id=%s
        """, (Jsonb(generation or {}), schedule_id, team_id))
        return self.get_schedule(schedule_id, team_id)

    def touch_generation(self, schedule_id: str, team_id: str, at: str) -> None:
        """Stamp liveness on a running job without rewriting the document.

        A single key is patched because the worker that beats and the loop
        that checkpoints write the same row at different moments: a
        read-modify-write of the whole document would let a heartbeat
        overwrite a day that finished while it was in flight. Scoped to
        `status = 'running'` so a late beat cannot revive a finished job.
        """
        self._execute("""
            UPDATE schedules
               SET generation = jsonb_set(
                       COALESCE(generation, '{}'::jsonb),
                       '{heartbeat}', to_jsonb(%s::text), true
                   )
             WHERE id=%s AND team_id=%s
               AND generation->>'status' = 'running'
        """, (at, schedule_id, team_id))

    def delete_schedule(self, schedule_id: str, team_id: str) -> None:
        """Remove a period and everything hanging off it.

        `change_log` rows survive by design (D4); their `schedule_id` goes
        NULL via the FK. The row is read first so another team's period
        answers 404 rather than a silent no-op reported as success.
        """
        self._require_schedule(schedule_id, team_id)
        self._execute(
            "DELETE FROM schedules WHERE id=%s AND team_id=%s",
            (schedule_id, team_id),
        )

    # -- slots ---------------------------------------------------------------

    def replace_slots(
        self, schedule_id: str, team_id: str, slots: List[dict]
    ) -> List[dict]:
        """Rebuild this schedule's slot grid in one transaction.

        A schedule that is half old grid and half new is not a state any
        reader should be able to observe.
        """
        self._require_schedule(schedule_id, team_id)
        with connect(self._store) as connection:
            connection.execute(
                "DELETE FROM shift_slots WHERE schedule_id=%s AND team_id=%s",
                (schedule_id, team_id),
            )
            for slot in slots:
                connection.execute("""
                    INSERT INTO shift_slots (
                        id, team_id, schedule_id, shift_name, slot_date,
                        start_time, end_time, headcount, required_roles,
                        requires_shift_manager, is_on_call
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (schedule_id, shift_name, slot_date)
                    DO NOTHING
                """, _slot_values(team_id, schedule_id, slot))
            _touch(connection, schedule_id)
            connection.commit()
        return self.slots(schedule_id, team_id)

    def slots(self, schedule_id: str, team_id: str) -> List[dict]:
        return self._all("""
            SELECT * FROM shift_slots
            WHERE schedule_id=%s AND team_id=%s
            ORDER BY slot_date, start_time, shift_name
        """, (schedule_id, team_id))

    def find_slot(
        self, schedule_id: str, team_id: str, shift_name: str, slot_date: str
    ) -> Optional[dict]:
        rows = self._all("""
            SELECT * FROM shift_slots
            WHERE schedule_id=%s AND team_id=%s
              AND shift_name=%s AND slot_date=%s
        """, (schedule_id, team_id, shift_name, slot_date))
        return rows[0] if rows else None

    def _require_schedule(self, schedule_id: str, team_id: str) -> None:
        """Raise unless this schedule belongs to this team.

        Called before any write that takes a schedule id from the caller, so
        a write can never land in another workspace's schedule -- and a miss
        reads as "not found" rather than "not yours".
        """
        self._one(
            "SELECT id FROM schedules WHERE id=%s AND team_id=%s",
            (schedule_id, team_id),
        )


def _slot_values(team_id: str, schedule_id: str, slot: dict) -> tuple:
    return (
        new_id(), team_id, schedule_id,
        slot["shift_name"], slot["slot_date"],
        slot.get("start_time", ""), slot.get("end_time", ""),
        int(slot.get("headcount", 1)),
        Jsonb(slot.get("required_roles") or []),
        bool(slot.get("requires_shift_manager", False)),
        bool(slot.get("is_on_call", False)),
    )


def _touch(connection, schedule_id: str) -> None:
    connection.execute(
        "UPDATE schedules SET updated_at=NOW() WHERE id=%s", (schedule_id,),
    )
