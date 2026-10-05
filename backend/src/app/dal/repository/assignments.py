"""Who is on which slot. **`assignments.reason` is never blank** (D8).

An assignment written without the agent's reasoning defeats the decision
quietly, at the one moment the manager would have caught a bad call cheaply,
so every write path here refuses one.
"""

from typing import List, Optional

from app.common.errors.errors import AgentError, NotFoundError
from app.dal.database.postgres import connect
from app.dal.repository.base import RepositoryBase, new_id
from app.dal.repository.schedule_vocabulary import (
    ASSIGNED_BY_AGENT, ASSIGNMENT_SOURCES,
)

_REASON_REQUIRED = "כל שיבוץ חייב לשאת נימוק של הסוכן"
_INSERT = """
    INSERT INTO assignments (
        id, team_id, schedule_id, slot_id, employee, reason, source
    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (slot_id, employee) DO NOTHING
"""
_ROW_WITH_SLOT = """
    SELECT a.id, a.employee, a.reason, a.slot_id, a.source{extra},
           s.shift_name AS shift, s.slot_date AS date
    FROM assignments a
    JOIN shift_slots s ON s.id = a.slot_id
"""


def _require_reasons(assignments: List[dict]) -> None:
    for item in assignments:
        if not (item.get("reason") or "").strip():
            raise AgentError(_REASON_REQUIRED)


def _insert_all(connection, team_id: str, schedule_id: str, assignments: List[dict]) -> None:
    for item in assignments:
        connection.execute(_INSERT, (
            new_id(), team_id, schedule_id, item["slot_id"],
            item["employee"], item["reason"].strip(),
            item.get("source") or ASSIGNED_BY_AGENT,
        ))


def _touch(connection, schedule_id: str) -> None:
    connection.execute(
        "UPDATE schedules SET updated_at=NOW() WHERE id=%s", (schedule_id,),
    )


class AssignmentRepository(RepositoryBase):
    def assignments(self, schedule_id: str, team_id: str) -> List[dict]:
        """Every assignment, joined to the slot that gives it a date.

        Shaped the way `bl/audit` wants its rows -- employee, shift, date --
        so the audit does not have to re-join what SQL already knows.
        """
        return self._all("""
            SELECT a.id, a.employee, a.reason, a.slot_id, a.source,
                   a.created_at,
                   s.shift_name AS shift, s.slot_date AS date,
                   s.start_time, s.end_time, s.is_on_call
            FROM assignments a
            JOIN shift_slots s ON s.id = a.slot_id
            WHERE a.schedule_id=%s AND a.team_id=%s
            ORDER BY s.slot_date, s.start_time, s.shift_name, a.employee
        """, (schedule_id, team_id))

    def replace_assignments(
        self, schedule_id: str, team_id: str, assignments: List[dict]
    ) -> List[dict]:
        """Rebuild the whole roster for this schedule, in one transaction."""
        self._require_schedule(schedule_id, team_id)
        _require_reasons(assignments)
        with connect(self._store) as connection:
            connection.execute(
                "DELETE FROM assignments WHERE schedule_id=%s AND team_id=%s",
                (schedule_id, team_id),
            )
            _insert_all(connection, team_id, schedule_id, assignments)
            _touch(connection, schedule_id)
            connection.commit()
        return self.assignments(schedule_id, team_id)

    def replace_span_assignments(
        self, schedule_id: str, team_id: str, dates: List[str],
        assignments: List[dict],
    ) -> List[dict]:
        """Rewrite the rows on these dates. **Every other date is untouched.**

        Rewriting the period per day was quadratic and lossy at once: a
        thirty-day build re-inserted every earlier day thirty times, and each
        rewrite minted fresh ids, so an `assignment_id` the browser held
        pointed at nothing. Deleting by date makes the work proportional to
        the span, and a row nobody touched keeps its identity.
        """
        self._require_schedule(schedule_id, team_id)
        _require_reasons(assignments)
        wanted = [date for date in dates if date]
        if not wanted:
            return self.assignments(schedule_id, team_id)
        with connect(self._store) as connection:
            connection.execute("""
                DELETE FROM assignments
                WHERE schedule_id=%s AND team_id=%s AND slot_id IN (
                    SELECT id FROM shift_slots
                    WHERE schedule_id=%s AND slot_date = ANY(%s)
                )
            """, (schedule_id, team_id, schedule_id, wanted))
            _insert_all(connection, team_id, schedule_id, assignments)
            _touch(connection, schedule_id)
            connection.commit()
        return self.assignments(schedule_id, team_id)

    def move_assignment(
        self, assignment_id: str, team_id: str, slot_id: str, reason: str,
        employee: Optional[str] = None,
    ) -> dict:
        """Move one assignment to another slot, or hand it to someone else.

        What a drag resolves to *after* the manager confirms it. The new
        reason is required for the same reason the original was (D8), and
        `source` is left alone: dragging a hand-placed shift does not make it
        the agent's.
        """
        if not (reason or "").strip():
            raise AgentError("העברת שיבוץ חייבת לשאת נימוק")
        with connect(self._store) as connection:
            row = _locked_row(connection, assignment_id, team_id, slot_id)
            connection.execute("""
                UPDATE assignments
                SET slot_id=%s, employee=%s, reason=%s
                WHERE id=%s AND team_id=%s
            """, (
                slot_id, employee or row["employee"], reason.strip(),
                assignment_id, team_id,
            ))
            _touch(connection, row["schedule_id"])
            connection.commit()
        return self._one(
            _ROW_WITH_SLOT.format(extra=", a.schedule_id")
            + " WHERE a.id=%s AND a.team_id=%s",
            (assignment_id, team_id),
        )

    def add_assignment(
        self, schedule_id: str, team_id: str, slot_id: str,
        employee: str, reason: str, source: str = ASSIGNED_BY_AGENT,
    ) -> dict:
        """Place one person on one slot.

        `source` says where the row came from (D18). `reason` is required
        whatever the source: a manually placed row carries the manager's own
        sentence -- a different voice answering D8, not an exemption from it.
        """
        if not (reason or "").strip():
            raise AgentError(_REASON_REQUIRED)
        if source not in ASSIGNMENT_SOURCES:
            raise AgentError("מקור שיבוץ לא מוכר")
        self._require_schedule(schedule_id, team_id)
        self._execute(_INSERT, (
            new_id(), team_id, schedule_id, slot_id, employee, reason.strip(), source,
        ))
        return self._one(
            _ROW_WITH_SLOT.format(extra="")
            + " WHERE a.slot_id=%s AND a.employee=%s AND a.team_id=%s",
            (slot_id, employee, team_id),
        )

    def remove_assignment(self, assignment_id: str, team_id: str) -> None:
        self._execute(
            "DELETE FROM assignments WHERE id=%s AND team_id=%s",
            (assignment_id, team_id),
        )


def _locked_row(connection, assignment_id: str, team_id: str, slot_id: str) -> dict:
    """The assignment being moved, after checking both ends exist."""
    row = connection.execute(
        "SELECT * FROM assignments WHERE id=%s AND team_id=%s",
        (assignment_id, team_id),
    ).fetchone()
    if row is None:
        raise NotFoundError("השיבוץ לא נמצא")
    target = connection.execute(
        "SELECT * FROM shift_slots WHERE id=%s AND team_id=%s", (slot_id, team_id),
    ).fetchone()
    if target is None:
        raise NotFoundError("המשמרת לא נמצאה")
    return row
