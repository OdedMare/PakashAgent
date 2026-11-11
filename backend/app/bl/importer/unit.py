"""Extract a unit draft from lists and schedules; never store assignments."""

import re
from collections import Counter, defaultdict

from app.bl.importer.cells import is_weekday, normalise, parse_date, parse_hours
from app.bl.importer.detect import detect
from app.bl.importer.files import MAX_COLUMNS, MAX_ROWS, read_grids
from app.bl.importer.marks import is_unavailable, split_names, split_note
from app.bl.importer.roster import _clean, match_people
from app.bl.importer.vocabulary import ShiftVocabulary

_NAME_HEADERS = {"שם", "שמות", "שם מלא", "שם החייל", "שם העובד", "חייל", "חיילים", "עובד", "עובדים"}
_SHIFT_HEADERS = {"משמרת", "משמרות", "שם המשמרת", "שם משמרת"}
_DEFAULTS = {"בוקר": ("06:00", "14:00"), "צהריים": ("14:00", "22:00"),
             "ערב": ("14:00", "22:00"), "לילה": ("22:00", "06:00")}


def preview_unit(content: bytes, filename: str, profile=None) -> dict:
    profile = profile or {}
    grids = read_grids(content, filename)
    names, shift_names, sources, warnings, explicit_hours = {}, {}, [], [], {}
    placements = defaultdict(set)
    for title, grid in grids:
        if len(grid) >= MAX_ROWS or any(len(row) >= MAX_COLUMNS for row in grid):
            warnings.append("%s: הגיליון הגיע למגבלת הקריאה; ייתכן שמידע נוסף לא חולץ" % title)
        for index, row in enumerate(grid[:12]):
            for column, value in enumerate(row):
                heading = normalise(value)
                target = names if heading in _NAME_HEADERS else shift_names if heading in _SHIFT_HEADERS else None
                if target is not None:
                    for line in grid[index + 1:]:
                        if column < len(line):
                            _add(target, line[column], title, target is shift_names)
        # Seed detection with names from explicit lists and familiar shift
        # headings, so first-time setup does not depend on an existing roster.
        for row in grid:
            for value in row:
                if normalise(value).removeprefix("משמרת ") in _DEFAULTS or parse_hours(value):
                    _add(shift_names, value, title, True)
        for row in grid:
            times = ["%02d:%02d" % tuple(map(int, value.split(":")[:2]))
                     for value in row if re.fullmatch(r"\d{1,2}:\d{2}(?::00)?", value)]
            if len(times) == 2 and parse_hours("-".join(times)):
                for value in row:
                    if value in shift_names:
                        explicit_hours[value] = times
        seed = dict(profile,
                    employees=list(profile.get("employees") or []) + [{"name": name} for name in names],
                    shifts=list(profile.get("shifts") or []) + [{"name": name} for name in shift_names])
        ranked = detect(grid, seed, ShiftVocabulary.from_profile(seed))
        if ranked:
            _score, confidence, reading = ranked[0]
            for name in reading.labels:
                _add(names, name, title)
            for item in reading.assignments + reading.unavailability:
                _add(names, item["employee"], title)
                _add(shift_names, item["shift"], title, True)
            for item in reading.assignments:
                placements[(item["shift"], item["date"])].add(_clean(item["employee"]))
            if confidence < .75:
                warnings.append("%s: יש לבדוק את החילוץ מול הגיליון" % title)
        sources.append({"name": title, "rows": len(grid),
                        "preview": [row[:30] for row in grid[:8]],
                        "recognized": bool(ranked or any(title in origin for origin in
                                                         list(names.values()) + list(shift_names.values())))})
    matches = match_people(names, profile)
    people = []
    for name, origin in names.items():
        match = matches[name]
        people.append({"name": name, "sources": origin,
                       "existing": match["employee"] if match["status"] == "exact" else "",
                       "candidates": match["candidates"]})
    existing = {row["name"]: row for row in profile.get("shifts") or []}
    shifts = []
    for name, origin in shift_names.items():
        hours = parse_hours(name)
        start, end = hours.split("-") if hours else _DEFAULTS.get(
            normalise(name).removeprefix("משמרת "), ("08:00", "16:00"))
        if name in explicit_hours:
            start, end = explicit_hours[name]
        counts = Counter(len(people) for (shift, _date), people in placements.items() if shift == name)
        count = counts.most_common(1)[0][0] if counts else 1
        saved = existing.get(name)
        shifts.append({"name": name, "start_time": start, "end_time": end,
                       "headcount": min(count, 100), "sources": origin,
                       "hours_source": "file" if hours or name in explicit_hours else "default",
                       "counts": sorted(counts), "existing": saved})
    if not people:
        warnings.append("לא זוהו חיילים. אפשר להוסיף ידנית בשלב החיילים")
    if not shifts:
        warnings.append("לא זוהו משמרות. אפשר להוסיף ידנית בשלב המשמרות")
    warnings.append("השעות והתקנים הם הצעה לבדיקה; צבעי תאים לבדם אינם מוכיחים שיבוץ")
    return {"filename": filename, "sheets": sources, "people": people,
            "shifts": shifts, "warnings": warnings}


def _add(target, value, source, shift=False):
    for part in split_names(value):
        name = re.sub(r"\s+", " ", part if shift else split_note(part)[0]).strip()
        if (not name or len(name) > 200 or not (any(c.isalpha() for c in name) or (shift and parse_hours(name)))
                or normalise(name) in _NAME_HEADERS | _SHIFT_HEADERS
                or is_unavailable(name) or is_weekday(name) or parse_date(name)):
            continue
        key = next((old for old in target if _clean(old) == _clean(name)), name)
        if source not in target.setdefault(key, []):
            target[key].append(source)
