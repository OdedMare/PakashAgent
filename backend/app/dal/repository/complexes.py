"""A מכלול: several workplaces joined under one commander (D43).

A team stays the tenant. These queries read across the teams of one מכלול,
and only those: every read that returns a team's data is filtered on
`complex_teams`, so a commander can never be handed a workplace that is
not linked to them. A team may be linked to several מכלולים (D56), each
link with its `access`: `edit` (every power, D43) or `view` (the board
only). The operator's reads (every מכלול, every team) are here
too, kept apart by name (`admin_*`).

The commander's password is hashed exactly as a team's (`teams.py`).
"""

from typing import Any, Dict, List, Optional

from app.common.errors import AuthError, NotFoundError
from app.dal.database import connect
from app.dal.repository.base import RepositoryBase, new_id
from app.dal.repository.teams import hash_password, verify_password

_COMPLEX_COLUMNS = "c.id, c.name, c.notes, c.active, c.created_at"

# Columns the operator may set directly. Built from these names, never the
# caller's keys, so a patch cannot name a column into the SQL.
_EDITABLE = ("name", "notes", "active")

# Repeats of the same action within this window fold into one notice.
_FOLD_MINUTES = 10

EDIT, VIEW = "edit", "view"


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
            SELECT t.id, t.name, t.active, ct.access, ct.complex_id
            FROM complex_teams ct JOIN teams t ON t.id = ct.team_id
            ORDER BY t.name
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

    def set_complex_teams(
        self, complex_id: str, team_ids: List[str],
        view_ids: Optional[List[str]] = None,
    ) -> None:
        """Make exactly `team_ids` the teams of this מכלול (D56).

        A team may be in several מכלולים. Those in `view_ids` are linked for
        viewing only, the rest for editing; with `view_ids` None a team
        already linked keeps its access and a new one edits. A team
        unlinked, or turned to viewing, loses this מכלול's duties from
        today on: they would block days nobody can cancel any more (D44).
        Past ones stay, as history and in the statistics.
        """
        wanted = sorted(set(team_ids))
        views = None if view_ids is None else set(view_ids) & set(wanted)
        with connect(self._store) as connection:
            exists = connection.execute(
                "SELECT id FROM complexes WHERE id=%s FOR UPDATE", (complex_id,)
            ).fetchone()
            if exists is None:
                raise NotFoundError("המכלול לא נמצא")
            if wanted:
                found = connection.execute(
                    "SELECT id FROM teams WHERE id = ANY(%s)", (wanted,),
                ).fetchall()
                if len(found) != len(wanted):
                    raise NotFoundError("אחד הצוותים לא נמצא")
            connection.execute(
                "DELETE FROM complex_teams "
                "WHERE complex_id=%s AND NOT (team_id = ANY(%s))",
                (complex_id, wanted),
            )
            for team_id in wanted:
                if views is None:
                    connection.execute("""
                        INSERT INTO complex_teams (complex_id, team_id, access)
                        VALUES (%s,%s,%s) ON CONFLICT DO NOTHING
                    """, (complex_id, team_id, EDIT))
                else:
                    access = VIEW if team_id in views else EDIT
                    connection.execute("""
                        INSERT INTO complex_teams (complex_id, team_id, access)
                        VALUES (%s,%s,%s) ON CONFLICT (complex_id, team_id)
                        DO UPDATE SET access = EXCLUDED.access
                    """, (complex_id, team_id, access))
            connection.execute("""
                DELETE FROM complex_duties d
                WHERE d.complex_id=%s AND d.duty_date >= CURRENT_DATE
                  AND NOT EXISTS (
                      SELECT 1 FROM complex_teams ct
                      WHERE ct.complex_id = d.complex_id
                        AND ct.team_id = d.team_id AND ct.access = 'edit')
            """, (complex_id,))
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
        """The workplaces of one מכלול, with their shift types, headcount
        and what this מכלול may do there (`access`, D56)."""
        rows = self._all("""
            SELECT t.id, t.name, t.active, ct.access, p.profile
            FROM complex_teams ct JOIN teams t ON t.id = ct.team_id
            LEFT JOIN team_profiles p ON p.team_id = t.id
            WHERE ct.complex_id=%s ORDER BY t.name
        """, (complex_id,))
        return [_team_summary(row) for row in rows]

    def team_in_complex(self, team_id: str, complex_id: str) -> bool:
        """True while this מכלול may *edit* this team and both are on: what
        entering it, its chats and its duties need (D56). A viewing link
        is not enough."""
        rows = self._all("""
            SELECT 1 FROM complex_teams ct
            JOIN teams t ON t.id = ct.team_id
            JOIN complexes c ON c.id = ct.complex_id
            WHERE ct.team_id=%s AND ct.complex_id=%s AND ct.access = 'edit'
              AND t.active AND c.active
        """, (team_id, complex_id))
        return bool(rows)

    def team_complexes(self, team_id: str) -> List[dict]:
        """Every מכלול this team is linked to, with its access, by name."""
        return self._all("""
            SELECT c.id, c.name, ct.access FROM complex_teams ct
            JOIN complexes c ON c.id = ct.complex_id
            WHERE ct.team_id=%s ORDER BY c.name
        """, (team_id,))

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
        "access": row.get("access") or EDIT,
        "has_profile": bool(row.get("profile")),
        "shifts": shifts,
        "employees": len([item for item in employees if item]),
    }


__all__ = ["ComplexRepository"]
