"""The operator's reads and writes across every workspace (D28).

Everything else in this package is scoped to one `team_id` on purpose -- a
forgotten WHERE clause there is a leak between workplaces. This module is
the deliberate exception: the צוות משמרות זהב console is above the tenants,
so its queries read across them. It is kept in its own mixin so that
exception is one file a reviewer can read, rather than a handful of unscoped
queries scattered among the scoped ones.

Nothing here returns `password_hash` or a passcode hash. The team columns
are named explicitly for the same reason `_public()` in the workspace
service names them: a `SELECT *` is one added column away from a leak.
"""

from typing import Any, Dict, List, Optional

from app.common.errors.errors import NotFoundError
from app.dal.database.postgres import connect
from app.dal.repository.base import RepositoryBase
from app.dal.repository.seats import roster_size

# The columns of `teams` the console may see. Not the hash, ever; the member
# token only in the single-team detail, where the operator may need to hand
# the link over again.
_TEAM_COLUMNS = "t.id, t.name, t.created_at, t.active, t.max_employees, t.notes"

# One row per team with its counts, read in a single round trip. The profile
# comes from the newest completed interview, matching `team_profile()`.
_TEAM_STATS = """
    SELECT """ + _TEAM_COLUMNS + """,
        p.profile -> 'employees' AS roster,
        (p.profile IS NOT NULL) AS has_profile,
        CASE WHEN jsonb_typeof(p.profile -> 'shifts') = 'array'
             THEN jsonb_array_length(p.profile -> 'shifts') ELSE 0 END
            AS shifts,
        (SELECT count(*) FROM employee_identities i
            WHERE i.team_id = t.id) AS identities,
        (SELECT count(*) FROM schedules s
            WHERE s.team_id = t.id) AS periods,
        (SELECT count(*) FROM schedules s
            WHERE s.team_id = t.id AND s.status = 'published') AS published,
        (SELECT count(*) FROM constraint_requests r
            WHERE r.team_id = t.id AND r.status = 'pending') AS pending_requests,
        (SELECT count(*) FROM swap_requests w
            WHERE w.team_id = t.id AND w.status = 'pending') AS pending_swaps,
        GREATEST(
            t.created_at,
            (SELECT max(c.created_at) FROM change_log c WHERE c.team_id = t.id),
            (SELECT max(s.updated_at) FROM schedules s WHERE s.team_id = t.id),
            (SELECT max(i.last_seen_at) FROM employee_identities i
                WHERE i.team_id = t.id),
            (SELECT max(v.updated_at) FROM interview_sessions v
                WHERE v.team_id = t.id)
        ) AS last_activity
    FROM teams t
    LEFT JOIN LATERAL (
        SELECT profile FROM interview_sessions
        WHERE team_id = t.id AND status = 'complete' AND profile IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT 1
    ) p ON TRUE
"""

# The fields `update_team_admin` may set, and nothing else. A dict of
# column -> value is built from these names, never from the caller's keys,
# so a patch cannot name a column into the SQL.
_EDITABLE = ("name", "max_employees", "active", "notes")


class AdminRepository(RepositoryBase):
    def admin_teams(self) -> List[dict]:
        """Every workspace with its headline numbers, newest first."""
        rows = self._all(_TEAM_STATS + " ORDER BY t.created_at DESC")
        return [_with_headcount(row) for row in rows]

    def admin_team(self, team_id: str) -> dict:
        """One workspace in full: counts, roster, claims, periods, history."""
        rows = self._all(_TEAM_STATS + " WHERE t.id = %s", (team_id,))
        if not rows:
            raise NotFoundError("הצוות לא נמצא")
        team = _with_headcount(rows[0])
        team["member_token"] = self._one(
            "SELECT member_token FROM teams WHERE id=%s", (team_id,)
        )["member_token"]
        team["profile_employees"] = _roster_rows(rows[0].get("roster"))
        team["identities_list"] = self._all("""
            SELECT employee, created_at, last_seen_at
            FROM employee_identities WHERE team_id=%s
            ORDER BY employee
        """, (team_id,))
        team["periods_list"] = self._all("""
            SELECT s.id, s.starts_on, s.ends_on, s.status, s.updated_at,
                (SELECT count(*) FROM assignments a
                    WHERE a.schedule_id = s.id) AS assignments
            FROM schedules s WHERE s.team_id=%s
            ORDER BY s.starts_on DESC
            LIMIT 24
        """, (team_id,))
        team["recent_changes"] = self._all("""
            SELECT action, employee, replaced_employee, slot_date,
                shift_name, reason, created_at
            FROM change_log WHERE team_id=%s
            ORDER BY created_at DESC
            LIMIT 15
        """, (team_id,))
        return team

    def admin_totals(self) -> dict:
        """Server-wide figures for the console's overview row."""
        rows = self._all("""
            SELECT
                (SELECT count(*) FROM teams) AS teams,
                (SELECT count(*) FROM teams WHERE active) AS active_teams,
                (SELECT count(*) FROM employee_identities) AS identities,
                (SELECT count(*) FROM schedules) AS periods,
                (SELECT count(*) FROM assignments) AS assignments,
                (SELECT count(*) FROM change_log) AS changes,
                (SELECT count(*) FROM constraint_requests
                    WHERE status = 'pending') AS pending_requests,
                pg_database_size(current_database()) AS database_bytes
        """)
        return dict(rows[0]) if rows else {}

    def update_team_admin(self, team_id: str, fields: Dict[str, Any]) -> None:
        """Apply the operator's edit. Unknown keys are ignored, not trusted."""
        chosen = [(name, fields[name]) for name in _EDITABLE if name in fields]
        if not chosen:
            return
        assignments = ", ".join("%s=%%s" % name for name, _ in chosen)
        values = [value for _, value in chosen] + [team_id]
        with connect(self._store) as connection:
            updated = connection.execute(
                "UPDATE teams SET " + assignments + " WHERE id=%s RETURNING id",
                values,
            ).fetchone()
            connection.commit()
        if updated is None:
            raise NotFoundError("הצוות לא נמצא")

    def delete_team(self, team_id: str) -> None:
        """Remove a workspace and everything that hangs off it.

        Every team-owned table references `teams(id) ON DELETE CASCADE`, so
        this one statement is the whole deletion -- schedules, assignments,
        the change log, identities, requests, chats, the interview. There is
        no soft delete and no undo; suspending (`active=FALSE`) is the
        reversible version, and the console offers it first.
        """
        with connect(self._store) as connection:
            deleted = connection.execute(
                "DELETE FROM teams WHERE id=%s RETURNING id", (team_id,)
            ).fetchone()
            connection.commit()
        if deleted is None:
            raise NotFoundError("הצוות לא נמצא")

    def team_is_active(self, team_id: str) -> bool:
        """False for a suspended team and for one that no longer exists."""
        rows = self._all("SELECT active FROM teams WHERE id=%s", (team_id,))
        return bool(rows and rows[0]["active"])


def _with_headcount(row: dict) -> dict:
    """Swap the raw roster JSON for the counts the console shows."""
    team = dict(row)
    roster = team.pop("roster", None)
    team["employees"] = roster_size({"employees": roster})
    team["roster_total"] = len(roster) if isinstance(roster, list) else 0
    return team


def _roster_rows(roster: Optional[Any]) -> List[dict]:
    """Name, role and status per employee -- never their notes or
    constraints, which are the manager's, not the operator's."""
    if not isinstance(roster, list):
        return []
    rows = []
    for item in roster:
        if isinstance(item, str):
            rows.append({"name": item, "role": "", "inactive_from": None})
        elif isinstance(item, dict) and str(item.get("name") or "").strip():
            rows.append({
                "name": str(item["name"]).strip(),
                "role": str(item.get("role") or ""),
                "service_type": str(item.get("service_type") or ""),
                "inactive_from": item.get("inactive_from"),
            })
    return rows


__all__ = ["AdminRepository"]
