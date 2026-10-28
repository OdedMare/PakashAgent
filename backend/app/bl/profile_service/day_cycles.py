"""Validating `workplace.day_cycles`: 11/3, 12/2, שבוע־שבוע and the like."""

import datetime
import re
from typing import Any, Dict, List

from app.bl.profile_service.validation import text, text_list, valid_time
from app.common.errors import AgentError

_MAX_CYCLE_DAYS = 120
MAX_DAY_SHIFT = 3
_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def day_cycles(value: Any) -> List[dict]:
    """Each cycle normalised; ids unique, so a person's pointer stays stable."""
    if not isinstance(value, list):
        raise AgentError("מחזורי היציאות אינם תקינים")
    result, seen = [], set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise AgentError("הגדרת מחזור יציאות אינה תקינה")
        row = _cycle(raw, index)
        if row["id"] in seen:
            raise AgentError("מזהה המחזור %s מופיע יותר מפעם אחת" % row["id"])
        seen.add(row["id"])
        result.append(row)
    return result


def groups_by_pattern(cycles: List[dict]) -> Dict[str, tuple]:
    """`cycle:<id>` -> its groups, the shape the other validators read."""
    return {"cycle:%s" % row["id"]: tuple(row["groups"]) for row in cycles}


def _cycle(raw: dict, index: int) -> dict:
    cycle_id = text(raw.get("id")) or "c%d" % (index + 1)
    if not _ID.match(cycle_id):
        raise AgentError("מזהה המחזור אינו תקין")
    base, home = _days(raw.get("base_days"), "ימי בסיס"), _days(raw.get("home_days"), "ימי בית")
    if base < 1 or home < 1 or base + home > _MAX_CYCLE_DAYS:
        raise AgentError("מחזור חייב לכלול לפחות יום בסיס ויום בית אחד, ועד %d ימים" % _MAX_CYCLE_DAYS)
    groups = list(dict.fromkeys(text_list(raw.get("groups") or ["א"])))
    if not groups:
        raise AgentError("למחזור יציאות חייבת להיות לפחות קבוצה אחת")
    anchor = text(raw.get("anchor_date"))
    if anchor:
        try:
            datetime.date.fromisoformat(anchor)
        except ValueError:
            raise AgentError("תאריך העוגן של המחזור אינו תקין")
    row = {
        "id": cycle_id,
        "name": text(raw.get("name")) or "%d/%d" % (base, home),
        "base_days": base,
        "home_days": home,
        "anchor_date": anchor,
        "groups": groups,
        "offsets": _offsets(raw.get("offsets"), groups, base + home),
    }
    row.update(_timing(raw, partial=False))
    row["group_times"] = _group_times(raw.get("group_times"), groups)
    row["time_changes"] = _time_changes(raw.get("time_changes"), groups)
    _check_stretches(row)
    return row


def _timing(raw: dict, partial: bool) -> dict:
    """Departure and return: a day shift from the nominal day and an hour.

    A partial layer (per group, per date) keeps only what it states, so the
    cycle's own hours still fill the rest.
    """
    result = {}
    for key in ("leave_day", "return_day"):
        stated = raw.get(key)
        if stated in (None, ""):
            if not partial:
                result[key] = 0
            continue
        if isinstance(stated, bool) or not isinstance(stated, int) \
                or abs(stated) > MAX_DAY_SHIFT:
            raise AgentError("הזזת יום היציאה או החזרה חייבת להיות עד %d ימים" % MAX_DAY_SHIFT)
        result[key] = stated
    for key in ("leave_time", "return_time"):
        stated = text(raw.get(key))
        if stated and not valid_time(stated):
            raise AgentError("שעות היציאה והחזרה חייבות להיות בפורמט HH:MM")
        if stated or not partial:
            result[key] = "%02d:%02d" % tuple(int(part) for part in stated.split(":")) if stated else ""
    return result


def _group_times(value: Any, groups: List[str]) -> Dict[str, dict]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise AgentError("שעות היציאה של הקבוצות אינן תקינות")
    result = {}
    for group, raw in value.items():
        if text(group) not in groups or not isinstance(raw, dict):
            raise AgentError("שעות היציאה שייכות לקבוצה שאינה במחזור")
        layer = _timing(raw, partial=True)
        if layer:
            result[text(group)] = layer
    return result


def _time_changes(value: Any, groups: List[str]) -> List[dict]:
    """Dated changes, matched on the nominal departure day they cover."""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise AgentError("השינויים בשעות המחזור אינם תקינים")
    result = []
    for raw in value:
        if not isinstance(raw, dict):
            raise AgentError("שינוי בשעות המחזור אינו תקין")
        group = text(raw.get("group"))
        if group and group not in groups:
            raise AgentError("השינוי בשעות שייך לקבוצה שאינה במחזור")
        row = dict(_timing(raw, partial=True), group=group)
        for key in ("starts_on", "ends_on"):
            row[key] = text(raw.get(key))
            if row[key]:
                try:
                    datetime.date.fromisoformat(row[key])
                except ValueError:
                    raise AgentError("תאריך השינוי בשעות אינו תקין")
        if not row["starts_on"] or (row["ends_on"] and row["ends_on"] < row["starts_on"]):
            raise AgentError("לשינוי בשעות חייב להיות תאריך התחלה, וסיום שאינו מוקדם ממנו")
        result.append(row)
    return result


def _check_stretches(row: dict) -> None:
    """Every combination of layers still leaves time both home and on base."""
    for group in row["groups"]:
        base = dict(row, **row["group_times"].get(group, {}))
        layers = [base] + [dict(base, **change) for change in row["time_changes"]
                           if change["group"] in ("", group)]
        for when in layers:
            home = _minutes_between(row["home_days"], when["leave_day"], when["leave_time"],
                                    when["return_day"], when["return_time"])
            stay = _minutes_between(row["base_days"], when["return_day"], when["return_time"],
                                    when["leave_day"], when["leave_time"])
            if home <= 0 or stay <= 0:
                raise AgentError("שעות היציאה והחזרה של %s %s אינן משאירות זמן בבית ובבסיס"
                                 % (row["name"], group))


def _minutes_between(days: int, from_day: int, from_time: str, to_day: int, to_time: str) -> int:
    clock = lambda value: sum(int(part) * unit for part, unit in zip((value or "0:0").split(":"), (60, 1)))
    return (days + to_day - from_day) * 1440 + clock(to_time) - clock(from_time)


def _days(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentError("%s חייבים להיות מספר שלם" % label)
    return value


def _offsets(value: Any, groups: List[str], length: int) -> Dict[str, int]:
    """Only the offsets the manager stated; the rest spread evenly at read time."""
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise AgentError("היסטי הקבוצות במחזור אינם תקינים")
    result = {}
    for group, days in value.items():
        if text(group) not in groups:
            raise AgentError("ההיסט שייך לקבוצה שאינה במחזור")
        if isinstance(days, bool) or not isinstance(days, int) or not 0 <= days < length:
            raise AgentError("היסט קבוצה חייב להיות בין 0 ל־%d ימים" % (length - 1))
        result[text(group)] = days
    return result
