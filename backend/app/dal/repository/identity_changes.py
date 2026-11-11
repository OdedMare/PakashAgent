"""A profile save that renames soldiers or shifts, or deletes a soldier.

Every stored row names a person or a shift by the profile's string, so a
rename has to reach all of them in the same transaction as the profile, or
the board would be left showing a name the roster no longer has. The change
log is the exception: it is append-only (D4), so what it recorded under the
old name stays, and the rename is appended to it as an entry of its own.
"""

from typing import Dict, List, Optional

from psycopg.errors import SerializationFailure

from app.common.actor import current_actor
from app.common.errors import AgentError, ConflictError
from app.dal.database import atomic
from app.dal.repository.base import RepositoryBase, new_id

# Tables naming a person in a plain `employee` column, scoped by `team_id`.
# A מכלול duty names the soldier by team and roster name too.
_EMPLOYEE_TABLES = ("assignments", "availability", "duties",
                    "employee_identities", "constraint_requests", "complex_duties")
_RENAMED = "renamed"
_REMOVED = "removed"


class IdentityChangeRepository(RepositoryBase):
    def update_team_profile_with_identity_changes(
        self, team_id: str, profile: dict, expected_revision: Optional[int],
        employees: Dict[str, str], shifts: Dict[str, str], removed: List[str],
    ) -> dict:
        """Save `profile` and carry renames and deletions through every row."""
        try:
            with atomic(self._store) as connection:
                saved = self.update_team_profile(team_id, profile, expected_revision)
                for name in removed:
                    _remove_employee(connection, team_id, name)
                for old, new in employees.items():
                    _rename_employee(connection, team_id, old, new)
                for old, new in shifts.items():
                    _rename_shift(connection, team_id, old, new)
                return saved
        except SerializationFailure as exc:
            raise ConflictError("הנתונים השתנו במקביל. יש לרענן ולשמור שוב") from exc


def _log(connection, team_id, action, employee="", replaced="", schedule_id=None,
         slot_date=None, shift_name="", reason="") -> None:
    connection.execute("""
        INSERT INTO change_log (id, team_id, schedule_id, action, employee,
            replaced_employee, slot_date, shift_name, reason, agent_reason, actor)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'',%s)
    """, (new_id(), team_id, schedule_id, action, employee, replaced,
          slot_date, shift_name, reason, current_actor()))


def _rename_employee(connection, team_id: str, old: str, new: str) -> None:
    for table in _EMPLOYEE_TABLES:
        connection.execute(
            "UPDATE %s SET employee=%%s WHERE team_id=%%s AND employee=%%s" % table,
            (new, team_id, old),
        )
    for column in ("requester", "counterparty"):
        connection.execute(
            "UPDATE swap_requests SET %s=%%s WHERE team_id=%%s AND %s=%%s" % (column, column),
            (new, team_id, old),
        )
    connection.execute("""
        UPDATE agent_preferences SET subject=%s
        WHERE team_id=%s AND subject=%s AND kind<>'shift'
    """, (new, team_id, old))
    _log(connection, team_id, _RENAMED, employee=new, replaced=old,
         reason="שינוי שם בהגדרת היחידה: %s ← %s" % (new, old))


def _rename_shift(connection, team_id: str, old: str, new: str) -> None:
    clash = connection.execute("""
        SELECT 1 FROM shift_slots s JOIN schedules sc ON sc.id=s.schedule_id
        WHERE sc.team_id=%s AND s.shift_name=%s LIMIT 1
    """, (team_id, new)).fetchone()
    if clash is not None:
        raise AgentError("כבר שמורים סידורים עם משמרת בשם %s; יש לבחור שם אחר" % new)
    connection.execute("""
        UPDATE shift_slots s SET shift_name=%s FROM schedules sc
        WHERE sc.id=s.schedule_id AND sc.team_id=%s AND s.shift_name=%s
    """, (new, team_id, old))
    for table in ("availability", "constraint_requests"):
        connection.execute(
            "UPDATE %s SET shift_name=%%s WHERE team_id=%%s AND shift_name=%%s" % table,
            (new, team_id, old),
        )
    for column in ("requester_shift", "counterparty_shift"):
        connection.execute(
            "UPDATE swap_requests SET %s=%%s WHERE team_id=%%s AND %s=%%s" % (column, column),
            (new, team_id, old),
        )
    connection.execute("""
        UPDATE agent_preferences SET subject=%s
        WHERE team_id=%s AND subject=%s AND kind<>'employee'
    """, (new, team_id, old))
    _log(connection, team_id, _RENAMED, shift_name=new,
         reason="שינוי שם משמרת בהגדרת היחידה: %s ← %s" % (new, old))


def _remove_employee(connection, team_id: str, name: str) -> None:
    """A soldier added by mistake: their draft rows go, each one logged."""
    published = connection.execute("""
        SELECT 1 FROM assignments a JOIN schedules sc ON sc.id=a.schedule_id
        WHERE a.team_id=%s AND a.employee=%s AND sc.status='published' LIMIT 1
    """, (team_id, name)).fetchone()
    if published is not None:
        raise AgentError(
            "%s משובץ/ת בסידור מפורסם, ולכן לא ניתן למחוק אותו/ה. "
            "אפשר לתקן את השם, או להוציא מהסגל במסך הצוות" % name
        )
    rows = connection.execute("""
        DELETE FROM assignments a USING shift_slots s
        WHERE a.slot_id=s.id AND a.team_id=%s AND a.employee=%s
        RETURNING a.schedule_id, s.slot_date, s.shift_name
    """, (team_id, name)).fetchall()
    reason = "%s נמחק/ה מהגדרת היחידה" % name
    for row in rows:
        _log(connection, team_id, _REMOVED, employee=name,
             schedule_id=row["schedule_id"], slot_date=row["slot_date"],
             shift_name=row["shift_name"], reason=reason)
    for table in _EMPLOYEE_TABLES[1:]:
        connection.execute(
            "DELETE FROM %s WHERE team_id=%%s AND employee=%%s" % table, (team_id, name),
        )
    connection.execute("""
        DELETE FROM swap_requests WHERE team_id=%s AND (requester=%s OR counterparty=%s)
    """, (team_id, name, name))
    connection.execute("""
        DELETE FROM agent_preferences WHERE team_id=%s AND subject=%s AND kind<>'shift'
    """, (team_id, name))
