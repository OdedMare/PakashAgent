"""What the importer believes a sheet says, as the manager will confirm it.

The manager's corrections land here rather than in the reading: a name in
the file mapped to someone on the roster (or to nobody -- left out), a
shift heading mapped to a declared shift (or left out). The reading stays
what the file said; the interpretation is what will be stored, and it is
the only thing the manager sees before a write happens (D7).
"""

from typing import Dict, List, Optional, Tuple

import datetime

from app.bl.importer.cells import human_date, text
from app.bl.importer.headers import year_warnings
from app.bl.importer.layout import DATES_DOWN, LANES_PEOPLE, LANES_SHIFTS, Layout
from app.bl.importer.reader import Reading
from app.bl.importer.roster import AMBIGUOUS, EXACT, MATCHED, UNKNOWN, match_people
from app.bl.importer.vocabulary import ShiftVocabulary
from app.common.time_context import israel_today

# Longest run of days one import may store: the ceiling a calendar view reads.
MAX_IMPORT_DAYS = 62


def interpret(reading: Reading, profile: Optional[dict], vocabulary: ShiftVocabulary,
              names: Optional[Dict[str, str]] = None,
              shifts: Optional[Dict[str, str]] = None,
              window: Tuple[str, str] = ("", "")) -> dict:
    """The rows to store, with every name and shift accounted for.

    `window` keeps only the dates from its first to its last (either may be
    empty): a sheet holding a year is imported a month at a time."""
    names, shifts = names or {}, shifts or {}
    owners = [row["employee"] for row in reading.assignments + reading.unavailability]
    matches = match_people(owners, profile)
    people = _people(matches, owners, names)
    shift_rows = _shifts(reading.shifts(), vocabulary, shifts, reading.assignments)
    person = {row["name"]: row["employee"] for row in people}
    shift = {row["name"]: row["shift"] for row in shift_rows}
    assignments = _unique(_mapped(reading.assignments, person, shift, keep_unowned=False),
                          ("employee", "shift", "date"))
    absences = _unique(_mapped(reading.unavailability, person, shift, keep_unowned=True),
                       ("employee", "shift", "date"))
    every = sorted({row["date"] for row in assignments + absences})
    window = window if any(window) else _default_window(every)
    assignments, absences = _within(assignments, window), _within(absences, window)
    dates = sorted({row["date"] for row in assignments + absences})
    result = {
        "file_starts_on": every[0] if every else "",
        "file_ends_on": every[-1] if every else "",
        "people": people,
        "shifts": shift_rows,
        "dates": dates,
        "starts_on": dates[0] if dates else "",
        "ends_on": dates[-1] if dates else "",
        "assignments": assignments,
        "unavailability": absences,
        "assumed_week": reading.assumed_week,
        "window": list(window),
    }
    result["warnings"] = _warnings(reading, result)
    result["summary"] = summary(result)
    return result


def _default_window(dates: List[str]) -> Tuple[str, str]:
    """No window for a file one import can hold; else one calendar month --
    today's when the file covers it, otherwise the file's last -- so a year
    on one sheet opens on something storable instead of on an error."""
    if not dates or _days(dates[0], dates[-1]) <= MAX_IMPORT_DAYS:
        return "", ""
    today = israel_today().isoformat()[:7]
    months = sorted({day[:7] for day in dates})
    month = today if today in months else months[-1]
    first = month + "-01"
    following = (datetime.date.fromisoformat(first) + datetime.timedelta(days=32)).replace(day=1)
    return first, (following - datetime.timedelta(days=1)).isoformat()


def _within(rows: List[dict], window: Tuple[str, str]) -> List[dict]:
    first, last = window
    return [row for row in rows
            if (not first or row["date"] >= first) and (not last or row["date"] <= last)]


def describe(layout: Layout) -> str:
    """The layout in one Hebrew sentence, for the confirm screen."""
    time_axis = "תאריכים בשורה %d" if layout.orientation != DATES_DOWN else "תאריכים בעמודה %d"
    parts = [time_axis % (layout.header + 1)]
    if layout.nested:
        parts.append("ומתחתם שמות המשמרות")
    if layout.lanes == LANES_SHIFTS:
        parts.append("כל שורה היא משמרת ובתאים שמות העובדים"
                     if layout.orientation != DATES_DOWN
                     else "כל עמודה היא משמרת ובתאים שמות העובדים")
    elif layout.lanes == LANES_PEOPLE:
        lane = "כל שורה היא עובד" if layout.orientation != DATES_DOWN else "כל עמודה היא עובד"
        parts.append(lane + (" ובתא סימון שהוא משובץ" if layout.nested
                             else " ובתא המשמרת שלו"))
    else:
        parts.append("בתאים שמות העובדים")
    return ", ".join(parts)


def summary(result: dict) -> str:
    """The one sentence D7 asks for: what will be stored."""
    known = len({row["employee"] for row in result["assignments"]})
    parts = ["%d אנשים" % known]
    if result["dates"]:
        parts.append("%s עד %s" % (human_date(result["starts_on"]), human_date(result["ends_on"])))
    parts.append("%d משמרות" % len([row for row in result["shifts"] if row["shift"]]))
    parts.append("%d שיבוצים" % len(result["assignments"]))
    if result["unavailability"]:
        parts.append("%d סימוני אי־זמינות" % len(result["unavailability"]))
    return ", ".join(parts)


def _people(matches: Dict[str, dict], owners: List[str], names: Dict[str, str]) -> List[dict]:
    counts: Dict[str, int] = {}
    for owner in owners:
        if owner:
            counts[owner] = counts.get(owner, 0) + 1
    rows = []
    for name in sorted(counts):
        match = matches.get(name) or {"employee": None, "status": UNKNOWN, "candidates": []}
        employee = match["employee"] if match["status"] in (EXACT, MATCHED) else name
        status = match["status"]
        if name in names:
            employee, status = text(names[name]), "mapped" if text(names[name]) else "skipped"
        rows.append({"name": name, "employee": employee, "status": status,
                     "candidates": match["candidates"], "count": counts[name]})
    return rows


def _shifts(found: List[str], vocabulary: ShiftVocabulary, mapping: Dict[str, str],
            rows: List[dict]) -> List[dict]:
    names = list(found)
    if any(not row["shift"] for row in rows):
        names.append("")
    result = []
    for name in names:
        declared = vocabulary.declared(name) if name else ""
        shift = declared or name
        if name in mapping:
            shift = text(mapping[name])
        count = sum(1 for row in rows if row["shift"] == name)
        result.append({"name": name, "shift": shift, "declared": bool(
            vocabulary.declared(shift)) if shift else False, "count": count})
    return result


def _mapped(rows: List[dict], person: Dict[str, str], shift: Dict[str, str],
            keep_unowned: bool) -> List[dict]:
    found = []
    for row in rows:
        employee = person.get(row["employee"], "") if row["employee"] else ""
        name = shift.get(row["shift"], row["shift"])
        if row["employee"] and not employee:
            continue
        if not employee and not keep_unowned:
            continue
        if row["shift"] and not name:
            continue
        found.append(dict(row, employee=employee, shift=name))
    return found


def _days(first: str, last: str) -> int:
    return (datetime.date.fromisoformat(last) - datetime.date.fromisoformat(first)).days + 1


def _unique(rows: List[dict], fields: tuple) -> List[dict]:
    found, seen = [], set()
    for row in rows:
        key = tuple(row.get(field) for field in fields)
        if key not in seen:
            seen.add(key)
            found.append(row)
    return found


def _warnings(reading: Reading, result: dict) -> List[str]:
    notes = list(reading.notes) + year_warnings(result["dates"])
    if reading.assumed_week:
        notes.append("בקובץ יש ימים בשבוע בלי תאריכים — הונח השבוע שמתחיל ב־%s; "
                     "אפשר לשנות את תאריך ההתחלה" % human_date(reading.assumed_week))
    unknown = [row["name"] for row in result["people"] if row["status"] == UNKNOWN]
    if unknown:
        notes.append("%d שמות אינם ברשימת הצוות: %s" % (len(unknown), ", ".join(unknown[:6])))
    ambiguous = [row["name"] for row in result["people"] if row["status"] == AMBIGUOUS]
    if ambiguous:
        notes.append("%d שמות מתאימים ליותר מעובד אחד — בחר למי הכוונה" % len(ambiguous))
    # Rows that will be stored on a shift the workplace never declared, or
    # on none at all; a heading mapped to nothing is left out, not loose.
    loose = [row["name"] or "ללא משמרת" for row in result["shifts"]
             if row["count"] and not row["declared"] and (row["shift"] or not row["name"])]
    if loose:
        notes.append("משמרות שאינן מוגדרות בצוות: %s" % ", ".join(loose[:6]))
    if result["file_starts_on"] and (result["file_starts_on"], result["file_ends_on"]) \
            != (result["starts_on"], result["ends_on"]) and any(result["window"]):
        notes.append("הקובץ מכסה %s עד %s; מוצגים רק %s עד %s — אפשר לבחור טווח אחר"
                     % (human_date(result["file_starts_on"]), human_date(result["file_ends_on"]),
                        human_date(result["starts_on"]), human_date(result["ends_on"])))
    if result["dates"] and _days(result["starts_on"], result["ends_on"]) > MAX_IMPORT_DAYS:
        notes.append("הטווח שנבחר מכסה %d ימים; ייבוא אחד מכסה עד %d"
                     % (_days(result["starts_on"], result["ends_on"]), MAX_IMPORT_DAYS))
    orphans = sum(1 for row in result["unavailability"] if not row["employee"])
    if orphans:
        notes.append("%d סימוני אי־זמינות אינם משויכים לאדם ולא יישמרו" % orphans)
    return list(dict.fromkeys(notes))
