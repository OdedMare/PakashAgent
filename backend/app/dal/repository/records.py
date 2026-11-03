"""Constraints, stored preferences, and the append-only change log."""

from typing import List, Optional

from app.common.actor import current_actor
from app.common.errors import AgentError, NotFoundError
from app.dal.repository.base import RepositoryBase, new_id
from app.dal.repository.schedule_vocabulary import (
    PREFERENCE_ACTIVE, PREFERENCE_GENERAL, PREFERENCE_KINDS,
    PREFERENCE_STATUSES, SOURCE_MANAGER, SOURCES,
)


def _filtered(base: str, params: list, filters: List[tuple]) -> tuple:
    """`base` plus an `AND column op %s` per filter whose value is set."""
    query = base
    for clause, value in filters:
        if value:
            query += " AND " + clause
            params.append(value)
    return query, params


class AvailabilityRepository(RepositoryBase):
    def set_availability(
        self,
        team_id: str,
        employee: str,
        constraint_date: str,
        shift_name: str = "",
        available: bool = False,
        start_time: str = "",
        end_time: str = "",
        is_hard: bool = True,
        reason: str = "",
        source: str = SOURCE_MANAGER,
    ) -> dict:
        """Record a constraint, replacing any it duplicates.

        An empty `shift_name` means the whole day. Upserted rather than
        appended: two rows saying the same thing would double every warning.
        """
        if source not in SOURCES:
            raise AgentError("מקור האילוץ אינו תקין")
        self._execute("""
            INSERT INTO availability (
                id, team_id, employee, constraint_date, shift_name,
                available, start_time, end_time, is_hard, reason, source
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (team_id, employee, constraint_date, shift_name)
            DO UPDATE SET
                available=EXCLUDED.available,
                start_time=EXCLUDED.start_time,
                end_time=EXCLUDED.end_time,
                is_hard=EXCLUDED.is_hard,
                reason=EXCLUDED.reason,
                source=EXCLUDED.source
        """, (new_id(), team_id, employee, constraint_date, shift_name or "",
              bool(available), start_time or "", end_time or "", bool(is_hard),
              reason or "", source))
        return self._one("""
            SELECT * FROM availability
            WHERE team_id=%s AND employee=%s AND constraint_date=%s
              AND shift_name=%s
        """, (team_id, employee, constraint_date, shift_name or ""))

    def availability(
        self, team_id: str, starts_on: Optional[str] = None,
        ends_on: Optional[str] = None, employee: Optional[str] = None,
    ) -> List[dict]:
        """Availability and blocking duties, in one scheduling shape."""
        query = """
            SELECT * FROM (
                SELECT id, team_id, employee, constraint_date, shift_name,
                       available, start_time, end_time, is_hard, reason,
                       source, created_at, 'availability' AS constraint_type
                FROM availability
                UNION ALL
                SELECT id, team_id, employee, duty_date AS constraint_date,
                       '' AS shift_name, FALSE AS available,
                       start_time, end_time, TRUE AS is_hard, reason,
                       source, created_at, 'duty' AS constraint_type
                FROM duties
                UNION ALL
                -- A מכלול duty holds the soldier for the whole day: no
                -- hours, which `audit/constraints.py` reads as the day from
                -- midnight to midnight.
                SELECT cd.id, cd.team_id, cd.employee,
                       cd.duty_date AS constraint_date, '' AS shift_name,
                       FALSE AS available, '' AS start_time, '' AS end_time,
                       TRUE AS is_hard, dt.name AS reason,
                       'complex' AS source, cd.created_at,
                       'duty' AS constraint_type
                FROM complex_duties cd
                JOIN complex_duty_types dt ON dt.id = cd.duty_type_id
                WHERE cd.blocks
            ) AS scheduling_constraints
            WHERE team_id=%s
        """
        params: List[object] = [team_id]
        if starts_on:
            # The previous day's overnight duty may overlap the first shift.
            query += " AND constraint_date >= %s::date - CASE WHEN constraint_type='duty' THEN 1 ELSE 0 END"
            params.append(starts_on)
        if ends_on:
            # And the next day's duty may overlap the last night shift.
            query += " AND constraint_date <= %s::date + CASE WHEN constraint_type='duty' THEN 1 ELSE 0 END"
            params.append(ends_on)
        if employee:
            query += " AND employee=%s"
            params.append(employee)
        query += " ORDER BY constraint_date, employee, shift_name"
        return self._all(query, tuple(params))

    def set_duty(
        self, team_id: str, employee: str, duty_date: str,
        start_time: str, end_time: str, reason: str = "",
        source: str = SOURCE_MANAGER,
    ) -> dict:
        if source not in SOURCES:
            raise AgentError("מקור התורנות אינו תקין")
        row_id = new_id()
        self._execute("""
            INSERT INTO duties (
                id, team_id, employee, duty_date, start_time, end_time,
                reason, source
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (row_id, team_id, employee, duty_date, start_time, end_time,
              reason or "", source))
        return self._one("""
            SELECT id, team_id, employee, duty_date AS constraint_date,
                   '' AS shift_name, FALSE AS available,
                   start_time, end_time, TRUE AS is_hard, reason, source,
                   created_at, 'duty' AS constraint_type
            FROM duties WHERE id=%s AND team_id=%s
        """, (row_id, team_id))

    def delete_availability(self, row_id: str, team_id: str) -> None:
        if self._all(
            "SELECT 1 FROM complex_duties WHERE id=%s AND team_id=%s",
            (row_id, team_id),
        ):
            raise AgentError("תורנות מכלול נקבעת ומבוטלת על ידי מפקד המכלול")
        self._execute(
            "DELETE FROM availability WHERE id=%s AND team_id=%s", (row_id, team_id),
        )
        self._execute(
            "DELETE FROM duties WHERE id=%s AND team_id=%s", (row_id, team_id),
        )


class PreferenceRepository(RepositoryBase):
    """`suggested` changes nothing until approved; `archived` keeps the record."""

    def create_preference(
        self, team_id: str, text: str, kind: str = PREFERENCE_GENERAL,
        subject: str = "", evidence: str = "",
        status: str = PREFERENCE_ACTIVE, source: str = SOURCE_MANAGER,
    ) -> dict:
        """Store one operational preference for a team.

        An agent-proposed row lands `suggested` and changes nothing until the
        manager approves it -- the `constraint_requests` shape (D14) applied
        to preferences.
        """
        if not (text or "").strip():
            raise AgentError("ההעדפה אינה יכולה להיות ריקה")
        if status not in PREFERENCE_STATUSES:
            raise AgentError("סטטוס ההעדפה אינו תקין")
        if kind not in PREFERENCE_KINDS:
            raise AgentError("סוג ההעדפה אינו תקין")
        row_id = new_id()
        self._execute("""
            INSERT INTO agent_preferences (
                id, team_id, kind, subject, text, evidence, status, source
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (row_id, team_id, kind, (subject or "").strip(),
              text.strip(), (evidence or "").strip(), status, source))
        return self.get_preference(row_id, team_id)

    def get_preference(self, row_id: str, team_id: str) -> dict:
        row = self._one(
            "SELECT * FROM agent_preferences WHERE id=%s AND team_id=%s",
            (row_id, team_id),
        )
        if row is None:
            raise NotFoundError("ההעדפה לא נמצאה")
        return row

    def preferences(self, team_id: str, status: Optional[str] = None) -> List[dict]:
        """A team's preferences, newest first; every state when unfiltered."""
        query, params = _filtered(
            "SELECT * FROM agent_preferences WHERE team_id=%s", [team_id],
            [("status=%s", status)],
        )
        return self._all(query + " ORDER BY created_at DESC", tuple(params))

    def update_preference(
        self, row_id: str, team_id: str, text: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict:
        """Edit a preference's wording, its status, or both.

        Approving a suggestion is this call with `status='active'`.
        """
        if status is not None and status not in PREFERENCE_STATUSES:
            raise AgentError("סטטוס ההעדפה אינו תקין")
        if text is not None and not text.strip():
            raise AgentError("ההעדפה אינה יכולה להיות ריקה")
        self.get_preference(row_id, team_id)
        self._execute("""
            UPDATE agent_preferences
               SET text = COALESCE(%s, text),
                   status = COALESCE(%s, status),
                   updated_at = NOW()
             WHERE id=%s AND team_id=%s
        """, (text.strip() if text is not None else None, status, row_id, team_id))
        return self.get_preference(row_id, team_id)

    def delete_preference(self, row_id: str, team_id: str) -> None:
        self._execute(
            "DELETE FROM agent_preferences WHERE id=%s AND team_id=%s",
            (row_id, team_id),
        )


class ChangeLogRepository(RepositoryBase):
    """**Append-only.** There is no update and no delete here, and there must
    not be: it is the only history the system keeps (D4)."""

    def append_change(
        self, team_id: str, action: str, schedule_id: Optional[str] = None,
        employee: str = "", replaced_employee: str = "",
        slot_date: Optional[str] = None, shift_name: str = "",
        reason: str = "", agent_reason: str = "",
    ) -> dict:
        """Append one entry. Both reasons are stored because they answer
        different questions (D8); `actor` is who was acting, from
        `common/actor.py` rather than from every caller."""
        row_id = new_id()
        self._execute("""
            INSERT INTO change_log (
                id, team_id, schedule_id, action, employee,
                replaced_employee, slot_date, shift_name, reason, agent_reason,
                actor
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (row_id, team_id, schedule_id, action, employee,
              replaced_employee, slot_date, shift_name, reason, agent_reason,
              current_actor()))
        return self._one(
            "SELECT * FROM change_log WHERE id=%s AND team_id=%s", (row_id, team_id),
        )

    def change_log(
        self, team_id: str, schedule_id: Optional[str] = None, limit: int = 100,
    ) -> List[dict]:
        """The history, newest first."""
        query, params = _filtered(
            "SELECT * FROM change_log WHERE team_id=%s", [team_id],
            [("schedule_id=%s", schedule_id)],
        )
        params.append(int(limit))
        return self._all(query + " ORDER BY created_at DESC, id LIMIT %s", tuple(params))
