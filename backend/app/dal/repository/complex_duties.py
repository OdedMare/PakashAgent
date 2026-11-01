"""A מכלול's duties: the types its commander defines and who stands them.

Like `complexes.py`, these reads cross the teams of one מכלול and only
those. Every write names the מכלול and checks inside the SQL itself that
the duty type and the soldier's team both belong to it, so a commander
holding another מכלול's ids gets a `NotFoundError`, never a row.

A team's own reads (`team_complex_duties`) are scoped by `team_id` like
every other workplace read; the scheduling projection of these rows lives
beside the team's own duties in `records.availability()`.
"""

from typing import Any, Dict, List, Optional

from app.common.errors import ConflictError, NotFoundError
from app.dal.database import connect
from app.dal.repository.base import RepositoryBase, new_id

_TYPE_COLUMNS = "id, complex_id, name, seats, days, weight, active, created_at"

# Columns a commander may set on a duty type. Built from these names, never
# the caller's keys, so a patch cannot name a column into the SQL.
_TYPE_EDITABLE = ("name", "seats", "days", "weight", "active")

_DUTY_COLUMNS = """
    d.id, d.complex_id, d.duty_type_id, dt.name AS duty_type, dt.weight,
    d.team_id, t.name AS team_name, d.employee, d.duty_date, d.note,
    d.blocks, d.created_at
"""

_DUTY_FROM = """
    FROM complex_duties d
    JOIN complex_duty_types dt ON dt.id = d.duty_type_id
    JOIN teams t ON t.id = d.team_id
"""


class ComplexDutyRepository(RepositoryBase):
    # --- duty types ----------------------------------------------------------

    def complex_duty_types(self, complex_id: str) -> List[dict]:
        return self._all(
            "SELECT " + _TYPE_COLUMNS + " FROM complex_duty_types "
            "WHERE complex_id=%s ORDER BY active DESC, name",
            (complex_id,),
        )

    def create_complex_duty_type(
        self, complex_id: str, name: str, seats: int = 1,
        days: Optional[List[str]] = None, weight: int = 1,
    ) -> dict:
        type_id = new_id()
        with connect(self._store) as connection:
            created = connection.execute("""
                INSERT INTO complex_duty_types
                    (id, complex_id, name, seats, days, weight)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (complex_id, name) DO NOTHING RETURNING id
            """, (type_id, complex_id, name, seats, list(days or []), weight)
            ).fetchone()
            connection.commit()
        if created is None:
            raise ConflictError("כבר קיימת תורנות בשם הזה")
        return self.complex_duty_type(complex_id, type_id)

    def complex_duty_type(self, complex_id: str, type_id: str) -> dict:
        rows = self._all(
            "SELECT " + _TYPE_COLUMNS + " FROM complex_duty_types "
            "WHERE id=%s AND complex_id=%s",
            (type_id, complex_id),
        )
        if not rows:
            raise NotFoundError("סוג התורנות לא נמצא")
        return rows[0]

    def update_complex_duty_type(
        self, complex_id: str, type_id: str, fields: Dict[str, Any],
    ) -> dict:
        self.complex_duty_type(complex_id, type_id)
        columns = [name for name in _TYPE_EDITABLE if name in fields]
        if columns:
            assignments = ", ".join("%s=%%s" % name for name in columns)
            params = [fields[name] for name in columns] + [type_id, complex_id]
            with connect(self._store) as connection:
                try:
                    connection.execute(
                        "UPDATE complex_duty_types SET " + assignments
                        + " WHERE id=%s AND complex_id=%s",
                        tuple(params),
                    )
                    connection.commit()
                except Exception as error:  # a renamed type hit another's name
                    connection.rollback()
                    if getattr(error, "sqlstate", "") == "23505":
                        raise ConflictError("כבר קיימת תורנות בשם הזה")
                    raise
        return self.complex_duty_type(complex_id, type_id)

    def delete_complex_duty_type(self, complex_id: str, type_id: str) -> None:
        """Removes the type and every assignment of it, past ones included.
        Retiring a type that has history is `active=False`, not this."""
        self.complex_duty_type(complex_id, type_id)
        self._execute(
            "DELETE FROM complex_duty_types WHERE id=%s AND complex_id=%s",
            (type_id, complex_id),
        )

    # --- who stands which duty -----------------------------------------------

    def complex_duties(
        self, complex_id: str, starts_on: str, ends_on: str,
    ) -> List[dict]:
        return self._all(
            "SELECT " + _DUTY_COLUMNS + _DUTY_FROM
            + " WHERE d.complex_id=%s AND d.duty_date BETWEEN %s AND %s"
            " ORDER BY d.duty_date, dt.name, t.name, d.employee",
            (complex_id, starts_on, ends_on),
        )

    def set_complex_duty(
        self, complex_id: str, type_id: str, team_id: str, employee: str,
        duty_date: str, note: str = "", blocks: bool = True,
    ) -> dict:
        """Seat one soldier on one duty for one day. `blocks=False` records
        one that counts without blocking the day.

        The INSERT selects its own guards: no row is written unless the
        type and the team both belong to this מכלול right now."""
        duty_id = new_id()
        with connect(self._store) as connection:
            guard = connection.execute("""
                SELECT 1 FROM complex_duty_types dt, teams t
                WHERE dt.id=%s AND dt.complex_id=%s
                  AND t.id=%s AND t.complex_id=%s
            """, (type_id, complex_id, team_id, complex_id)).fetchone()
            if guard is None:
                raise NotFoundError("סוג התורנות או המשמרת לא נמצאו במכלול")
            created = connection.execute("""
                INSERT INTO complex_duties
                    (id, complex_id, duty_type_id, team_id, employee,
                     duty_date, note, blocks)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (team_id, employee, duty_date) DO NOTHING
                RETURNING id
            """, (duty_id, complex_id, type_id, team_id, employee,
                  duty_date, note or "", bool(blocks))).fetchone()
            connection.commit()
        if created is None:
            raise ConflictError("%s כבר בתורנות בתאריך הזה" % employee)
        return self.complex_duty(complex_id, duty_id)

    def complex_duty(self, complex_id: str, duty_id: str) -> dict:
        rows = self._all(
            "SELECT " + _DUTY_COLUMNS + _DUTY_FROM
            + " WHERE d.id=%s AND d.complex_id=%s",
            (duty_id, complex_id),
        )
        if not rows:
            raise NotFoundError("התורנות לא נמצאה")
        return rows[0]

    def delete_complex_duty(self, complex_id: str, duty_id: str) -> dict:
        """Removes one assignment and returns it, for the change log."""
        row = self.complex_duty(complex_id, duty_id)
        self._execute(
            "DELETE FROM complex_duties WHERE id=%s AND complex_id=%s",
            (duty_id, complex_id),
        )
        return row

    def soldier_shifts(
        self, team_id: str, employee: str, starts_on: str, ends_on: str,
    ) -> List[dict]:
        """One soldier's stored shifts over a few dates, with each period's
        status -- what a duty on those dates would collide with."""
        return self._all("""
            SELECT a.id, a.schedule_id, s.status, sl.shift_name,
                   sl.slot_date, sl.start_time, sl.end_time
            FROM assignments a
            JOIN shift_slots sl ON sl.id = a.slot_id
            JOIN schedules s ON s.id = a.schedule_id
            WHERE a.team_id=%s AND a.employee=%s
              AND sl.slot_date BETWEEN %s AND %s
            ORDER BY sl.slot_date, sl.start_time
        """, (team_id, employee, starts_on, ends_on))

    def team_complex_duties(
        self, team_id: str, starts_on: str, ends_on: str,
        employee: Optional[str] = None,
    ) -> List[dict]:
        """One team's soldiers on מכלול duty, for its own manager to read."""
        query = (
            "SELECT " + _DUTY_COLUMNS + _DUTY_FROM
            + " WHERE d.team_id=%s AND d.duty_date BETWEEN %s AND %s"
        )
        params: List[object] = [team_id, starts_on, ends_on]
        if employee:
            query += " AND d.employee=%s"
            params.append(employee)
        return self._all(query + " ORDER BY d.duty_date, d.employee", tuple(params))
