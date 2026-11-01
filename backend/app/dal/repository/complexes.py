"""A מכלול: several workplaces joined under one commander (D43).

A team stays the tenant. These queries read across the teams of one מכלול,
and only those: every read that returns a team's data is filtered on
`teams.complex_id`, so a commander can never be handed a workplace that is
not linked to them. The operator's reads (every מכלול, every team) are here
too, kept apart by name (`admin_*`).

The commander's password is hashed exactly as a team's (`teams.py`).
"""

from typing import Any, Dict, List, Optional

from app.common.errors import AuthError, ConflictError, NotFoundError
from app.dal.database import connect
from app.dal.repository.base import RepositoryBase, new_id
from app.dal.repository.teams import hash_password, verify_password

_COMPLEX_COLUMNS = "c.id, c.name, c.notes, c.active, c.created_at"

# Columns the operator may set directly. Built from these names, never the
# caller's keys, so a patch cannot name a column into the SQL.
_EDITABLE = ("name", "notes", "active")

# Repeats of the same action within this window fold into one notice.
_FOLD_MINUTES = 10


class ComplexRepository(RepositoryBase):
    # --- the operator's side -------------------------------------------------

    def create_complex(self, name: str, password: str) -> dict:
        complex_id = new_id()
        self._execute(
            "INSERT INTO complexes (id, name, password_hash) VALUES (%s,%s,%s)",
            (complex_id, name, hash_password(password)),
        )
        return self.get_complex(complex_id)

    def get_complex(self, complex_id: str) -> dict:
        rows = self._all(
            "SELECT " + _COMPLEX_COLUMNS + " FROM complexes c WHERE c.id=%s",
            (complex_id,),
        )
        if not rows:
            raise NotFoundError("המכלול לא נמצא")
        return rows[0]

    def admin_complexes(self) -> List[dict]:
        """Every מכלול with the teams linked to it, newest first."""
        complexes = self._all(
            "SELECT " + _COMPLEX_COLUMNS
            + " FROM complexes c ORDER BY c.created_at DESC"
        )
        teams = self._all("""
            SELECT id, name, active, complex_id FROM teams
            WHERE complex_id IS NOT NULL ORDER BY name
        """)
        by_complex = {}  # type: Dict[str, List[dict]]
        for team in teams:
            by_complex.setdefault(team.pop("complex_id"), []).append(team)
        for row in complexes:
            row["teams"] = by_complex.get(row["id"], [])
        return complexes

    def update_complex(self, complex_id: str, fields: Dict[str, Any]) -> None:
        chosen = [(name, fields[name]) for name in _EDITABLE if name in fields]
        if not chosen:
            self.get_complex(complex_id)
            return
        assignments = ", ".join("%s=%%s" % name for name, _ in chosen)
        values = [value for _, value in chosen] + [complex_id]
        rows = self._all(
            "UPDATE complexes SET " + assignments + " WHERE id=%s RETURNING id",
            values,
        )
        if not rows:
            raise NotFoundError("המכלול לא נמצא")

    def set_complex_password(self, complex_id: str, password: str) -> None:
        rows = self._all(
            "UPDATE complexes SET password_hash=%s WHERE id=%s RETURNING id",
            (hash_password(password), complex_id),
        )
        if not rows:
            raise NotFoundError("המכלול לא נמצא")

    def set_complex_teams(self, complex_id: str, team_ids: List[str]) -> None:
        """Make exactly `team_ids` the teams of this מכלול.

        A team already linked to *another* מכלול is refused rather than
        moved: taking a workplace from one commander and giving it to another
        is a decision the operator should see named, not a side effect.
        """
        wanted = sorted(set(team_ids))
        with connect(self._store) as connection:
            exists = connection.execute(
                "SELECT id FROM complexes WHERE id=%s FOR UPDATE", (complex_id,)
            ).fetchone()
            if exists is None:
                raise NotFoundError("המכלול לא נמצא")
            if wanted:
                found = connection.execute(
                    "SELECT id, name, complex_id FROM teams WHERE id = ANY(%s)",
                    (wanted,),
                ).fetchall()
                if len(found) != len(wanted):
                    raise NotFoundError("אחד הצוותים לא נמצא")
                taken = [
                    row["name"] for row in found
                    if row["complex_id"] and row["complex_id"] != complex_id
                ]
                if taken:
                    raise ConflictError(
                        "כבר משויך למכלול אחר: " + ", ".join(taken)
                    )
            connection.execute(
                "UPDATE teams SET complex_id=NULL "
                "WHERE complex_id=%s AND NOT (id = ANY(%s))",
                (complex_id, wanted),
            )
            if wanted:
                connection.execute(
                    "UPDATE teams SET complex_id=%s WHERE id = ANY(%s)",
                    (complex_id, wanted),
                )
            connection.commit()

    def delete_complex(self, complex_id: str) -> None:
        """Teams are unlinked by the foreign key, never deleted."""
        rows = self._all(
            "DELETE FROM complexes WHERE id=%s RETURNING id", (complex_id,)
        )
        if not rows:
            raise NotFoundError("המכלול לא נמצא")

    # --- the commander's side -------------------------------------------------

    def list_complexes(self) -> List[dict]:
        """Names for the commander's login picker: active ones only."""
        return self._all(
            "SELECT id, name FROM complexes WHERE active ORDER BY name"
        )

    def authenticate_commander(self, complex_id: str, password: str) -> dict:
        """The מכלול if the password matches. A missing one costs the same
        time as a wrong password, as `authenticate_boss` does."""
        rows = self._all(
            "SELECT id, name, active, password_hash FROM complexes WHERE id=%s",
            (complex_id,),
        )
        row = rows[0] if rows else None
        stored = row["password_hash"] if row else hash_password("")
        if not verify_password(password, stored) or row is None:
            raise AuthError("שם המכלול או הסיסמה שגויים")
        row.pop("password_hash")
        return row

    def complex_is_active(self, complex_id: str) -> bool:
        rows = self._all(
            "SELECT active FROM complexes WHERE id=%s", (complex_id,)
        )
        return bool(rows and rows[0]["active"])

    def complex_teams(self, complex_id: str) -> List[dict]:
        """The workplaces of one מכלול, with their shift types and headcount."""
        rows = self._all("""
            SELECT t.id, t.name, t.active, p.profile
            FROM teams t LEFT JOIN team_profiles p ON p.team_id = t.id
            WHERE t.complex_id=%s ORDER BY t.name
        """, (complex_id,))
        return [_team_summary(row) for row in rows]

    def team_in_complex(self, team_id: str, complex_id: str) -> bool:
        """True while this team is linked to this מכלול and both are on."""
        rows = self._all("""
            SELECT 1 FROM teams t JOIN complexes c ON c.id = t.complex_id
            WHERE t.id=%s AND c.id=%s AND t.active AND c.active
        """, (team_id, complex_id))
        return bool(rows)

    def team_complex(self, team_id: str) -> Optional[dict]:
        rows = self._all("""
            SELECT c.id, c.name FROM teams t
            JOIN complexes c ON c.id = t.complex_id WHERE t.id=%s
        """, (team_id,))
        return rows[0] if rows else None

    # --- what the commander changed, for the manager ---------------------------

    def record_commander_notice(
        self, team_id: str, complex_name: str, action: str,
    ) -> None:
        with connect(self._store) as connection:
            folded = connection.execute("""
                UPDATE commander_notices SET count = count + 1, created_at = NOW()
                WHERE id = (
                    SELECT id FROM commander_notices
                    WHERE team_id=%s AND action=%s AND seen_at IS NULL
                      AND created_at > NOW() - make_interval(mins => %s)
                    ORDER BY created_at DESC LIMIT 1
                ) RETURNING id
            """, (team_id, action, _FOLD_MINUTES)).fetchone()
            if folded is None:
                connection.execute("""
                    INSERT INTO commander_notices
                        (id, team_id, complex_name, action)
                    VALUES (%s,%s,%s,%s)
                """, (new_id(), team_id, complex_name, action))
            connection.commit()

    def commander_notices(self, team_id: str, limit: int = 30) -> List[dict]:
        """Unseen notices, newest first."""
        return self._all("""
            SELECT id, complex_name, action, count, created_at
            FROM commander_notices WHERE team_id=%s AND seen_at IS NULL
            ORDER BY created_at DESC LIMIT %s
        """, (team_id, limit))

    def mark_commander_notices_seen(self, team_id: str) -> None:
        self._execute(
            "UPDATE commander_notices SET seen_at=NOW() "
            "WHERE team_id=%s AND seen_at IS NULL",
            (team_id,),
        )


def _team_summary(row: dict) -> dict:
    profile = row.get("profile") or {}
    shifts = []
    for shift in profile.get("shifts") or []:
        if isinstance(shift, dict) and shift.get("name"):
            shifts.append({
                "name": str(shift["name"]),
                "start_time": str(shift.get("start_time") or ""),
                "end_time": str(shift.get("end_time") or ""),
            })
    employees = profile.get("employees") or []
    return {
        "id": row["id"],
        "name": row["name"],
        "active": bool(row["active"]),
        "has_profile": bool(row.get("profile")),
        "shifts": shifts,
        "employees": len([item for item in employees if item]),
    }


__all__ = ["ComplexRepository"]
