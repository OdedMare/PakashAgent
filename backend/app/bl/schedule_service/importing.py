"""Importing the workplace's own spreadsheets (D7/D42): preview, then commit.

`ImportPreview` reads a file and says what it holds; it writes nothing.
`ImportCommitter` stores exactly the rows the manager approved -- taken
back from the caller rather than re-read from the file, so what is stored
is what was shown. A period that already exists for those dates is never
silently overwritten: the commit either opens a new period where none
exists, or, when the manager chose a draft, rewrites only the imported
shifts on the imported dates of that draft.
"""

import datetime
from typing import Dict, List, Optional

from app.bl.importer import infer, read_grids
from app.bl.importer.interpretation import MAX_IMPORT_DAYS as _MAX_DAYS
from app.bl.scheduler.slots import build_slots
from app.bl.schedule_service.constants import ACTION_IMPORTED, IMPORTED_REASON
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.rows import iso, slot_index, text
from app.common.errors import AgentError, AppError
from app.common.time_context import israel_today
from app.dal.repository.schedules import ASSIGNED_BY_IMPORT, SOURCE_MANAGER



class ImportPreview:
    def __init__(self, context: ScheduleContext, mapper=None):
        self._context = context
        self._mapper = mapper

    def preview(self, team_id: str, content: bytes, filename: str = "",
                sheet: str = "", layout: Optional[dict] = None, week_start: str = "",
                hint: str = "", names: Optional[Dict[str, str]] = None,
                shifts: Optional[Dict[str, str]] = None, use_model: bool = True,
                date_from: str = "", date_to: str = "", year: int = 0) -> dict:
        """What the file holds, read as the manager last corrected it."""
        profile = self._context.profile(team_id)
        grids = read_grids(content, filename)
        titles = [title for title, _grid in grids]
        title, grid = _sheet(grids, sheet, profile)
        result = infer(grid, profile, layout=layout,
                       mapper=self._mapper if use_model else None,
                       week_start=week_start, hint=hint, names=names, shifts=shifts,
                       date_from=date_from, date_to=date_to, year=year)
        result.update(filename=filename, sheets=titles, sheet_name=title,
                      overlaps=self._overlaps(team_id, result["starts_on"], result["ends_on"]))
        return result

    def _overlaps(self, team_id: str, starts_on: str, ends_on: str) -> List[dict]:
        if not starts_on:
            return []
        return [
            {"id": row["id"], "starts_on": iso(row["starts_on"]),
             "ends_on": iso(row["ends_on"]), "status": row.get("status") or "draft"}
            for row in self._context.repository.list_schedules(team_id)
            if iso(row["starts_on"]) <= ends_on and starts_on <= iso(row["ends_on"])
        ]


def _sheet(grids, wanted: str, profile: dict):
    """The sheet asked for, else the month on today, else the one detection
    reads most out of.

    A workbook often opens on an instructions tab, and a unit keeps one tab
    per month (אוקטובר, נובמבר, דצמבר); trying each tab without the model is
    cheap, and the one covering today is the one the manager is working in.
    """
    if wanted:
        for title, grid in grids:
            if title == wanted:
                return title, grid
        raise AgentError("הגיליון שנבחר לא נמצא בקובץ")
    if len(grids) == 1:
        return grids[0]
    today = israel_today().isoformat()
    best, best_key = grids[0], (False, -1.0)
    for title, grid in grids:
        try:
            found = infer(grid, profile)
        except AgentError:
            continue
        covers = found["file_starts_on"] <= today <= found["file_ends_on"]
        key = (covers, len(found["assignments"]) * found["confidence"])
        if key > best_key:
            best, best_key = (title, grid), key
    return best


class ImportCommitter:
    def __init__(self, context: ScheduleContext):
        self._context = context
        self._repository = context.repository

    def commit(self, team_id: str, assignments: List[dict],
               unavailability: Optional[List[dict]] = None,
               schedule_id: Optional[str] = None, filename: str = "") -> dict:
        """Store the approved rows: a new period, or into the chosen draft."""
        rows = _clean(assignments, require_employee=True)
        if not rows:
            raise AppError("אין שיבוצים לשמור")
        dates = sorted({row["date"] for row in rows})
        reason = IMPORTED_REASON + (" (%s)" % text(filename)[:80] if text(filename) else "")
        profile = self._context.profile(team_id)
        if schedule_id:
            schedule = self._merge(team_id, schedule_id, rows, dates, profile, reason)
        else:
            schedule = self._open(team_id, rows, dates, profile, reason)
        recorded = self._record_unavailability(team_id, unavailability)
        self._repository.append_change(
            team_id, ACTION_IMPORTED, schedule_id=schedule["id"],
            agent_reason="יובאו %d שיבוצים ו־%d אילוצים מקובץ%s" % (
                len(rows), recorded, " " + text(filename)[:80] if text(filename) else ""),
        )
        return self._context.fresh_view(schedule["id"], team_id)

    def _open(self, team_id, rows, dates, profile, reason) -> dict:
        _require_span(dates)
        clash = [row for row in self._repository.list_schedules(team_id)
                 if iso(row["starts_on"]) <= dates[-1] and dates[0] <= iso(row["ends_on"])]
        if clash:
            raise AppError(
                "כבר קיים סידור בתאריכים %s–%s. בחר למזג לתוכו, או מחק אותו קודם"
                % (iso(clash[0]["starts_on"]), iso(clash[0]["ends_on"])))
        schedule = self._repository.create_schedule(team_id, dates[0], dates[-1])
        stored = self._repository.replace_slots(schedule["id"], team_id,
                                                grid_of(profile, rows, dates))
        self._repository.replace_assignments(
            schedule["id"], team_id, _placements(rows, slot_index(stored), reason))
        return schedule

    def _merge(self, team_id, schedule_id, rows, dates, profile, reason) -> dict:
        """Into an existing draft: the imported shifts on the imported dates
        are rewritten, every other row stands."""
        schedule = self._context.require_schedule(team_id, schedule_id)
        if schedule.get("status") != "draft":
            raise AppError("אפשר למזג רק לתוך טיוטה; החזר את הסידור לטיוטה קודם")
        first, last = iso(schedule.get("starts_on")), iso(schedule.get("ends_on"))
        if dates[0] < first or dates[-1] > last:
            raise AppError("התאריכים בקובץ (%s–%s) חורגים מהסידור שנבחר (%s–%s)"
                             % (dates[0], dates[-1], first, last))
        stored = {(text(slot.get("shift_name")), iso(slot.get("slot_date")))
                  for slot in schedule.get("slots") or []}
        missing = [slot for slot in grid_of(profile, rows, dates)
                   if (slot["shift_name"], slot["slot_date"]) not in stored]
        if missing:
            self._repository.add_slots(schedule["id"], team_id, missing)
        slots = self._repository.get_schedule(schedule["id"], team_id).get("slots") or []
        shifts = sorted({row["shift"] for row in rows})
        self._repository.replace_span_assignments(
            schedule["id"], team_id, dates,
            _placements(rows, slot_index(slots), reason), shifts=shifts)
        return schedule

    def _record_unavailability(self, team_id: str, rows: Optional[List[dict]]) -> int:
        """Absences the sheet stated outright. Not `employee_reported` --
        nobody submitted these -- they are the manager's, which is what a
        sheet they kept makes them."""
        recorded = 0
        for row in _clean(rows, require_employee=True, require_shift=False):
            self._repository.set_availability(
                team_id, row["employee"], row["date"], shift_name=row["shift"],
                available=False, reason=text(row.get("reason"))[:200], source=SOURCE_MANAGER,
            )
            recorded += 1
        return recorded


def grid_of(profile: dict, rows: List[dict], dates: List[str]) -> List[dict]:
    """The slots an imported period needs.

    Every (shift, date) the file placed somebody on, plus the slots the
    profile plans for those shifts on the file's dates -- so a shift the file
    ran short shows as short rather than as never having run. A shift the
    profile does not declare gets a slot of its own sized by the file: a past
    schedule ran the shifts it actually ran (D9).
    """
    imported = {row["shift"] for row in rows}
    on_dates = set(dates)
    planned = {(slot["shift_name"], slot["slot_date"]): slot
               for slot in build_slots(profile, dates[0], dates[-1])
               if slot["shift_name"] in imported and slot["slot_date"] in on_dates}
    declared = {text(shift.get("name")): shift for shift in profile.get("shifts") or []
                if isinstance(shift, dict)}
    counts: Dict[tuple, int] = {}
    for row in rows:
        key = (row["shift"], row["date"])
        counts[key] = counts.get(key, 0) + 1
    for key, count in counts.items():
        if key not in planned:
            shift = declared.get(key[0]) or {}
            planned[key] = {
                "shift_name": key[0], "slot_date": key[1],
                "start_time": text(shift.get("start_time")),
                "end_time": text(shift.get("end_time")),
                "headcount": count, "is_on_call": bool(shift.get("is_on_call")),
            }
    return sorted(planned.values(), key=lambda slot: (slot["slot_date"], slot["shift_name"]))


def _clean(rows, require_employee: bool, require_shift: bool = True) -> List[dict]:
    found = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        clean = {"employee": text(row.get("employee")), "shift": text(row.get("shift")),
                 "date": iso(row.get("date")), "reason": text(row.get("reason"))}
        if not clean["date"] or (require_employee and not clean["employee"]):
            continue
        if require_shift and not clean["shift"]:
            raise AppError("יש שיבוצים ללא משמרת; בחר משמרת לכל השיבוצים לפני השמירה")
        found.append(clean)
    return found


def _require_span(dates: List[str]) -> None:
    first, last = (datetime.date.fromisoformat(day) for day in (dates[0], dates[-1]))
    if (last - first).days >= _MAX_DAYS:
        raise AppError("ייבוא אחד מכסה עד %d ימים; פצל את הקובץ או בחר גיליון אחר" % _MAX_DAYS)


def _placements(rows: List[dict], index: dict, reason: str) -> List[dict]:
    placements = []
    for row in rows:
        slot_id = index.get((row["shift"], row["date"]))
        if slot_id is not None:
            # The file's own word for the row ("חפיפה") rides on the reason.
            said = reason + (" — " + row["reason"][:60] if row.get("reason") else "")
            placements.append({"slot_id": slot_id, "employee": row["employee"],
                               "reason": said, "source": ASSIGNED_BY_IMPORT})
    return placements
