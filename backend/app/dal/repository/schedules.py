"""Schedule persistence: periods, slots, assignments, constraints, history.

Every read is scoped by `team_id`, and the team is a required argument rather
than an optional filter. A schedule id is a UUID and therefore hard to guess,
but "hard to guess" is not an access control -- one workspace's manager
holding another's schedule id must still get a `NotFoundError`, and a miss
across teams is never distinguished from a miss outright
([D10](../../../docs/DECISIONS.md#d10--one-workspace-per-team-the-boss-holds-a-password-members-hold-a-link)).

Two invariants are enforced here rather than left to callers:

- **`assignments.reason` is never blank.** Every assignment carries the
  agent's reasoning ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required)),
  and an assignment written without one defeats the decision quietly, at the
  one moment the manager would have caught a bad call cheaply.
- **`change_log` is append-only.** There is no update and no delete here, and
  there must not be: it is the only history the system keeps
  ([D4](../../../docs/DECISIONS.md#d4--living-schedule-not-versioned)).
"""

import datetime
from typing import List, Optional

from app.common.errors import AgentError, NotFoundError
from app.dal.database.postgres import connect
from app.dal.repository.base import RepositoryBase, new_id

# Where a constraint came from. `employee_reported` is the manager writing
# down what someone told them out of band -- employees have no account and
# never write here themselves (D5/D10), so this records provenance, not
# authorship.
SOURCE_MANAGER = "manager"
SOURCE_AGENT = "agent"
SOURCE_EMPLOYEE_REPORTED = "employee_reported"
SOURCE_INTERVIEW = "interview"
_SOURCES = (
    SOURCE_MANAGER, SOURCE_AGENT, SOURCE_EMPLOYEE_REPORTED, SOURCE_INTERVIEW,
)

# Where an *assignment* came from (D18). A narrower set than the constraint
# sources above and deliberately a separate tuple: a schedule row can only
# have been generated, placed by the manager, or read out of a file, and
# widening this to the constraint vocabulary would admit values that mean
# nothing here. Like `availability.source`, it records where the row came
# from -- not who typed it.
ASSIGNED_BY_AGENT = "agent"
ASSIGNED_BY_MANAGER = "manager"
ASSIGNED_BY_IMPORT = "imported"
_ASSIGNMENT_SOURCES = (
    ASSIGNED_BY_AGENT, ASSIGNED_BY_MANAGER, ASSIGNED_BY_IMPORT,
)


class ScheduleRepository(RepositoryBase):

    # -- schedules ---------------------------------------------------------

    def create_schedule(
        self, team_id: str, starts_on: str, ends_on: str
    ) -> dict:
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
        manager's working state and is not something the team should be
        looking at -- publishing is the act that makes it theirs.
        """
        clause = " AND status='published'" if published_only else ""
        rows = self._all("""
            SELECT id FROM schedules
            WHERE team_id=%s""" + clause + """
            ORDER BY
                (starts_on <= CURRENT_DATE AND ends_on >= CURRENT_DATE) DESC,
                starts_on DESC
            LIMIT 1
        """, (team_id,))
        if not rows:
            return None
        return self.get_schedule(rows[0]["id"], team_id)

    def set_schedule_status(
        self, schedule_id: str, team_id: str, status: str
    ) -> dict:
        if status not in ("draft", "published"):
            raise AgentError("סטטוס סידור לא תקין")
        self._execute("""
            UPDATE schedules SET status=%s, updated_at=NOW()
            WHERE id=%s AND team_id=%s
        """, (status, schedule_id, team_id))
        return self.get_schedule(schedule_id, team_id)

    def delete_schedule(self, schedule_id: str, team_id: str) -> None:
        """Remove a period and everything hanging off it.

        The `change_log` rows survive by design: they are the history of what
        was done, and history does not disappear because the thing it
        describes did (D4). Their `schedule_id` goes NULL via the FK.
        """
        self._execute(
            "DELETE FROM schedules WHERE id=%s AND team_id=%s",
            (schedule_id, team_id),
        )

    # -- slots -------------------------------------------------------------

    def replace_slots(
        self, schedule_id: str, team_id: str, slots: List[dict]
    ) -> List[dict]:
        """Rebuild this schedule's slot grid in one transaction.

        Generation produces the whole period at once, so the slots are
        replaced wholesale rather than diffed. Done in a single transaction
        because a schedule that is half old grid and half new is not a state
        any reader should be able to observe.
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
                        start_time, end_time, headcount, is_on_call
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (schedule_id, shift_name, slot_date)
                    DO NOTHING
                """, (
                    new_id(), team_id, schedule_id,
                    slot["shift_name"], slot["slot_date"],
                    slot.get("start_time", ""), slot.get("end_time", ""),
                    int(slot.get("headcount", 1)),
                    bool(slot.get("is_on_call", False)),
                ))
            connection.execute(
                "UPDATE schedules SET updated_at=NOW() WHERE id=%s",
                (schedule_id,),
            )
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

    # -- assignments -------------------------------------------------------

    def assignments(self, schedule_id: str, team_id: str) -> List[dict]:
        """Every assignment, joined to the slot that gives it a date.

        Shaped the way `bl/audit.py` wants its rows -- employee, shift, date
        -- so the audit does not have to re-join what SQL already knows.
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
        """Rebuild the whole roster for this schedule, in one transaction.

        Every row must carry the agent's reason; a blank one raises rather
        than being stored, because an assignment nobody can explain is
        exactly what D8 exists to prevent and the failure is silent later.
        """
        self._require_schedule(schedule_id, team_id)
        for item in assignments:
            if not (item.get("reason") or "").strip():
                raise AgentError("כל שיבוץ חייב לשאת נימוק של הסוכן")
        with connect(self._store) as connection:
            connection.execute(
                "DELETE FROM assignments WHERE schedule_id=%s AND team_id=%s",
                (schedule_id, team_id),
            )
            for item in assignments:
                connection.execute("""
                    INSERT INTO assignments (
                        id, team_id, schedule_id, slot_id, employee, reason,
                        source
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (slot_id, employee) DO NOTHING
                """, (
                    new_id(), team_id, schedule_id, item["slot_id"],
                    item["employee"], item["reason"].strip(),
                    item.get("source") or ASSIGNED_BY_AGENT,
                ))
            connection.execute(
                "UPDATE schedules SET updated_at=NOW() WHERE id=%s",
                (schedule_id,),
            )
            connection.commit()
        return self.assignments(schedule_id, team_id)

    def move_assignment(
        self,
        assignment_id: str,
        team_id: str,
        slot_id: str,
        reason: str,
        employee: Optional[str] = None,
    ) -> dict:
        """Move one assignment to another slot, or hand it to someone else.

        This is what a drag on the calendar resolves to *after* the manager
        confirms it. The new reason is required for the same reason the
        original was: the schedule must never hold a row whose presence
        nobody can account for (D8).
        """
        if not (reason or "").strip():
            raise AgentError("העברת שיבוץ חייבת לשאת נימוק")
        with connect(self._store) as connection:
            row = connection.execute("""
                SELECT * FROM assignments WHERE id=%s AND team_id=%s
            """, (assignment_id, team_id)).fetchone()
            if row is None:
                raise NotFoundError("השיבוץ לא נמצא")
            target = connection.execute("""
                SELECT * FROM shift_slots WHERE id=%s AND team_id=%s
            """, (slot_id, team_id)).fetchone()
            if target is None:
                raise NotFoundError("המשמרת לא נמצאה")
            connection.execute("""
                UPDATE assignments
                SET slot_id=%s, employee=%s, reason=%s
                WHERE id=%s AND team_id=%s
            """, (
                slot_id, employee or row["employee"], reason.strip(),
                assignment_id, team_id,
            ))
            connection.execute(
                "UPDATE schedules SET updated_at=NOW() WHERE id=%s",
                (row["schedule_id"],),
            )
            connection.commit()
        return self._one("""
            SELECT a.id, a.employee, a.reason, a.slot_id, a.schedule_id,
                   a.source,
                   s.shift_name AS shift, s.slot_date AS date
            FROM assignments a
            JOIN shift_slots s ON s.id = a.slot_id
            WHERE a.id=%s AND a.team_id=%s
        """, (assignment_id, team_id))

    def add_assignment(
        self, schedule_id: str, team_id: str, slot_id: str,
        employee: str, reason: str, source: str = ASSIGNED_BY_AGENT,
    ) -> dict:
        """Place one person on one slot.

        `source` says where the row came from (D18) and defaults to `agent`,
        so every existing caller keeps writing exactly what it wrote before.
        The manual path passes `manager`; the importer will pass `imported`.

        `reason` is required whatever the source. A manually placed row
        carries the manager's own sentence rather than the agent's, which is
        a different voice answering D8 -- not an exemption from it.
        """
        if not (reason or "").strip():
            raise AgentError("כל שיבוץ חייב לשאת נימוק של הסוכן")
        if source not in _ASSIGNMENT_SOURCES:
            raise AgentError("מקור שיבוץ לא מוכר")
        self._require_schedule(schedule_id, team_id)
        assignment_id = new_id()
        self._execute("""
            INSERT INTO assignments (
                id, team_id, schedule_id, slot_id, employee, reason, source
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (slot_id, employee) DO NOTHING
        """, (assignment_id, team_id, schedule_id, slot_id,
              employee, reason.strip(), source))
        return self._one("""
            SELECT a.id, a.employee, a.reason, a.slot_id, a.source,
                   s.shift_name AS shift, s.slot_date AS date
            FROM assignments a
            JOIN shift_slots s ON s.id = a.slot_id
            WHERE a.slot_id=%s AND a.employee=%s AND a.team_id=%s
        """, (slot_id, employee, team_id))

    def remove_assignment(self, assignment_id: str, team_id: str) -> None:
        self._execute(
            "DELETE FROM assignments WHERE id=%s AND team_id=%s",
            (assignment_id, team_id),
        )

    # -- availability ------------------------------------------------------

    def set_availability(
        self,
        team_id: str,
        employee: str,
        constraint_date: str,
        shift_name: str = "",
        available: bool = False,
        reason: str = "",
        source: str = SOURCE_MANAGER,
    ) -> dict:
        """Record a constraint, replacing any it duplicates.

        An empty `shift_name` means the whole day, which is how the interview
        asks the question and how `audit.py` reads it. Upserted rather than
        appended: a manager restating a constraint means the same one, and
        two rows saying the same thing would double every warning it causes.
        """
        if source not in _SOURCES:
            raise AgentError("מקור האילוץ אינו תקין")
        row_id = new_id()
        self._execute("""
            INSERT INTO availability (
                id, team_id, employee, constraint_date, shift_name,
                available, reason, source
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (team_id, employee, constraint_date, shift_name)
            DO UPDATE SET
                available=EXCLUDED.available,
                reason=EXCLUDED.reason,
                source=EXCLUDED.source
        """, (row_id, team_id, employee, constraint_date, shift_name or "",
              bool(available), reason or "", source))
        return self._one("""
            SELECT * FROM availability
            WHERE team_id=%s AND employee=%s AND constraint_date=%s
              AND shift_name=%s
        """, (team_id, employee, constraint_date, shift_name or ""))

    def availability(
        self,
        team_id: str,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
        employee: Optional[str] = None,
    ) -> List[dict]:
        """Constraints for a team, optionally windowed to a period."""
        query = "SELECT * FROM availability WHERE team_id=%s"
        params: List[object] = [team_id]
        if starts_on:
            query += " AND constraint_date >= %s"
            params.append(starts_on)
        if ends_on:
            query += " AND constraint_date <= %s"
            params.append(ends_on)
        if employee:
            query += " AND employee=%s"
            params.append(employee)
        query += " ORDER BY constraint_date, employee, shift_name"
        return self._all(query, tuple(params))

    def delete_availability(self, row_id: str, team_id: str) -> None:
        self._execute(
            "DELETE FROM availability WHERE id=%s AND team_id=%s",
            (row_id, team_id),
        )

    # -- change log --------------------------------------------------------

    def append_change(
        self,
        team_id: str,
        action: str,
        schedule_id: Optional[str] = None,
        employee: str = "",
        replaced_employee: str = "",
        slot_date: Optional[str] = None,
        shift_name: str = "",
        reason: str = "",
        agent_reason: str = "",
    ) -> dict:
        """Append one entry. There is no update and no delete, by design.

        Both reasons are stored because they answer different questions: the
        manager's `reason` is the record that makes "how many sick days has
        Dana taken" answerable at all, and the agent's is what justified this
        particular replacement (D8).
        """
        row_id = new_id()
        self._execute("""
            INSERT INTO change_log (
                id, team_id, schedule_id, action, employee,
                replaced_employee, slot_date, shift_name, reason, agent_reason
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (row_id, team_id, schedule_id, action, employee,
              replaced_employee, slot_date, shift_name, reason, agent_reason))
        return self._one(
            "SELECT * FROM change_log WHERE id=%s AND team_id=%s",
            (row_id, team_id),
        )

    def change_log(
        self, team_id: str, schedule_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """The history, newest first."""
        query = "SELECT * FROM change_log WHERE team_id=%s"
        params: List[object] = [team_id]
        if schedule_id:
            query += " AND schedule_id=%s"
            params.append(schedule_id)
        query += " ORDER BY created_at DESC, id LIMIT %s"
        params.append(int(limit))
        return self._all(query, tuple(params))

    # -- helpers -----------------------------------------------------------

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


def week_bounds(day: Optional[datetime.date] = None) -> tuple:
    """The Sunday-to-Saturday week containing `day`, as ISO strings.

    Sunday-based because the workweek here is Israeli: the source files run
    ראשון through שבת, and a Monday-based week would split every one of them
    across two schedules.
    """
    day = day or datetime.date.today()
    # `weekday()` is Monday=0; Sunday is 6, so this rolls back to Sunday.
    start = day - datetime.timedelta(days=(day.weekday() + 1) % 7)
    return start.isoformat(), (start + datetime.timedelta(days=6)).isoformat()


__all__ = [
    "ScheduleRepository", "week_bounds",
    "SOURCE_MANAGER", "SOURCE_AGENT", "SOURCE_EMPLOYEE_REPORTED",
    "SOURCE_INTERVIEW",
]
