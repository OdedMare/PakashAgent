"""Importing the workplace's own spreadsheets (D7): preview, then commit."""

from typing import List, Optional

from app.bl.importer import infer, read_grids
from app.bl.learn import observe
from app.bl.schedule_service.constants import ACTION_IMPORTED, IMPORTED_REASON
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.rows import iso, slot_index, text
from app.common.errors import AgentError
from app.dal.repository.schedules import ASSIGNED_BY_IMPORT, SOURCE_MANAGER


class ImportPreview:
    """Read uploaded files and say what they contain. Writes nothing.

    This is the whole of D7 on the service side: inference runs, the manager
    reads an interpretation, and **nothing reaches the database until
    `commit`**. Each file is inferred separately, because they were written
    at different times and may not share a layout, and then read *together*
    for patterns: a rule about how somebody works is only visible across
    periods. One unreadable file does not sink the batch.
    """

    def __init__(self, learner):
        self._learner = learner

    def preview(
        self, profile: dict, files: List[dict], learn_rules: bool = True
    ) -> dict:
        if not files:
            raise AgentError("לא נבחרו קבצים לייבוא")
        periods, failures, assignments, unavailability = [], [], [], []
        for item in files:
            for label, found in self._interpretations(item, profile, failures):
                periods.append(dict(found.to_dict(), filename=label))
                assignments.extend(found.assignments)
                unavailability.extend(found.unavailability)
        if not periods:
            raise AgentError(
                "לא הצלחתי לקרוא אף אחד מהקבצים. "
                "ודא שהם מכילים טבלת סידור עם תאריכים ושמות משמרות"
            )
        # Counted over every file together. A pattern is by definition
        # something one period cannot show.
        observations = observe(assignments, unavailability, profile)
        rules = self._rules(observations, profile, learn_rules)
        return {
            "periods": periods,
            "failures": failures,
            "observations": observations,
            "candidate_rules": rules["rules"],
            "notes": rules["notes"],
        }

    def _interpretations(
        self, item: dict, profile: dict, failures: List[dict]
    ) -> List[tuple]:
        """(label, interpretation) for every readable sheet of one file."""
        name = (item or {}).get("filename") or ""
        try:
            grids = read_grids((item or {}).get("content") or b"", name)
        except AgentError as error:
            failures.append({"filename": name, "error": str(error)})
            return []
        found = []
        for sheet_name, grid in grids:
            label = name
            if len(grids) > 1 and sheet_name:
                label = "%s — %s" % (name, sheet_name)
            try:
                found.append((label, infer(grid, profile)))
            except AgentError as error:
                failures.append({"filename": label, "error": str(error)})
        return found

    def _rules(self, observations: dict, profile: dict, learn: bool) -> dict:
        if not learn:
            return {"rules": [], "notes": []}
        try:
            return self._learner.propose(observations, profile)
        except AgentError as error:
            # The schedules were read successfully; only the rule suggestions
            # failed. Losing the import over an unavailable model would throw
            # away the expensive half of the work.
            return {"rules": [], "notes": [str(error)]}


class ImportCommitter:
    """Store an interpretation the manager has approved (D7).

    Takes the rows back from the caller rather than re-reading the file:
    what is stored must be exactly what was shown and approved. The slot grid
    is built from the imported rows, not from `build_slots` — a past schedule
    ran the shifts it actually ran, and regenerating the grid from today's
    vocabulary would quietly reshape history (D9). Every row lands with
    `source='imported'`.
    """

    def __init__(self, context: ScheduleContext):
        self._context = context
        self._repository = context.repository

    def commit(
        self,
        team_id: str,
        assignments: List[dict],
        unavailability: Optional[List[dict]] = None,
        starts_on: Optional[str] = None,
        ends_on: Optional[str] = None,
    ) -> dict:
        rows = [row for row in (assignments or []) if isinstance(row, dict)]
        if not rows:
            raise AgentError("אין שיבוצים לשמור")
        dates = sorted({iso(row.get("date")) for row in rows if iso(row.get("date"))})
        if not dates:
            raise AgentError("לשיבוצים המיובאים אין תאריכים תקינים")
        slots = _grid_of(rows)
        if not slots:
            raise AgentError("לא ניתן לבנות את מבנה הסידור מהקובץ")

        schedule = self._repository.create_schedule(
            team_id, starts_on or dates[0], ends_on or dates[-1]
        )
        stored = self._repository.replace_slots(schedule["id"], team_id, slots)
        placements = _placements(rows, slot_index(stored))
        self._repository.replace_assignments(schedule["id"], team_id, placements)
        recorded = self._record_unavailability(team_id, unavailability)
        self._repository.append_change(
            team_id, ACTION_IMPORTED, schedule_id=schedule["id"],
            agent_reason=(
                "יובאו %d שיבוצים ו-%d אילוצים מקובץ קיים"
                % (len(placements), recorded)
            ),
        )
        return self._context.fresh_view(schedule["id"], team_id)

    def _record_unavailability(
        self, team_id: str, unavailability: Optional[List[dict]]
    ) -> int:
        """Constraints the sheet stated outright travel with the schedule.

        `source='employee_reported'` would be a lie -- nobody submitted
        these -- so they are the manager's, which is what a sheet they
        maintained actually makes them.
        """
        recorded = 0
        for row in unavailability or []:
            if not isinstance(row, dict):
                continue
            employee, date = text(row.get("employee")), iso(row.get("date"))
            if not employee or not date:
                continue
            self._repository.set_availability(
                team_id, employee, date,
                shift_name=text(row.get("shift")),
                available=False,
                reason=text(row.get("reason")),
                source=SOURCE_MANAGER,
            )
            recorded += 1
        return recorded


def _grid_of(rows: List[dict]) -> List[dict]:
    """One slot per (shift, date) actually seen in the file.

    Deduplicated because several people on one shift is one slot with two
    assignments, not two slots.
    """
    slots, seen = [], set()
    for row in rows:
        key = (text(row.get("shift")), iso(row.get("date")))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        slots.append({"shift_name": key[0], "slot_date": key[1]})
    return slots


def _placements(rows: List[dict], index: dict) -> List[dict]:
    placements = []
    for row in rows:
        slot_id = index.get((text(row.get("shift")), iso(row.get("date"))))
        employee = text(row.get("employee"))
        if slot_id is None or not employee:
            continue
        placements.append({
            "slot_id": slot_id,
            "employee": employee,
            "reason": text(row.get("reason")) or IMPORTED_REASON,
            "source": ASSIGNED_BY_IMPORT,
        })
    return placements
