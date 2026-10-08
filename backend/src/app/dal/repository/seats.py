"""The seat cap: how many employees a workspace may carry (D28).

A quota, enforced here for the same reason a UNIQUE constraint is enforced in
the schema rather than in `bl/`: three different writers put a roster into
the database -- the interview completing, the profile editor, and an approved
chat plan -- and a rule each of them must remember to call is a rule one of
them eventually forgets. Every one of those writes already runs inside a
connection here, so the cap is read in the same transaction as the write.

**Only growth is refused.** A team whose cap the operator lowered below its
current headcount can still edit, reorder and remove people; it just cannot
add. Refusing every write over the cap would lock a manager out of the very
edit that brings them back under it.

**A departed employee does not hold a seat.** `inactive_from` on or before
today means they left; their past shifts still render, but they are not part
of the team the cap is counting.
"""

import datetime
from typing import Any, Optional

from app.common.errors.errors import ConflictError


def roster_size(profile: Any, today: Optional[datetime.date] = None) -> int:
    """Employees on the profile who still occupy a seat."""
    if not isinstance(profile, dict):
        return 0
    rows = profile.get("employees")
    if not isinstance(rows, list):
        return 0
    today = today or datetime.date.today()
    count = 0
    for row in rows:
        if isinstance(row, str):
            count += 1 if row.strip() else 0
            continue
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        if _departed(row.get("inactive_from"), today):
            continue
        count += 1
    return count


def guard_seats(connection, team_id: str, profile: Any, current: Any = None) -> None:
    """Refuse a roster that grows past the team's cap.

    `connection` is the caller's open one, so the cap is read in the same
    transaction as the write it guards.
    """
    row = connection.execute(
        "SELECT max_employees FROM teams WHERE id=%s", (team_id,)
    ).fetchone()
    limit = row["max_employees"] if row else None
    if limit is None:
        return
    wanted = roster_size(profile)
    if wanted <= limit or wanted <= roster_size(current):
        return
    raise ConflictError(
        "הצוות מוגבל ל-%d עובדים פעילים, והשינוי מביא ל-%d. "
        "להגדלת המכסה פנו לצוות משמרות זהב" % (limit, wanted)
    )


def _departed(value: Any, today: datetime.date) -> bool:
    if not value:
        return False
    try:
        return datetime.date.fromisoformat(str(value)[:10]) <= today
    except ValueError:
        return False


__all__ = ["roster_size", "guard_seats"]
