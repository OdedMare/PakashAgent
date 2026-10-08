"""What comes back from the model, bounded to what actually exists.

None of these rejections is a scheduling judgment
([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)):
a row is dropped because it is unusable -- no reason, a slot or person nobody
declared, or a day the rotation already says is not theirs -- never because
code disagreed with the choice.
"""

import datetime
from typing import Any, List, Optional

from app.bl.audit import constraint_conflicts
from app.bl.scheduler.rotation_rows import ROTATION_SOURCES
from app.bl.scheduler.values import bounded, parse_date
from app.common.errors.errors import AgentError

PINNED_REASON = "שיבוץ חובה שנבחר על ידי המנהל בעת בניית הסידור"


def _known_people(profile: dict) -> set:
    people = {
        bounded(person.get("name"))
        for person in (profile or {}).get("employees") or []
        if isinstance(person, dict)
    }
    people.discard("")
    return people


def bound_assignments(
    offered: Any, slots: List[dict], profile: dict,
    availability: Optional[List[dict]] = None,
) -> List[dict]:
    """The model's assignments, bounded to what actually exists.

    Four rejections: **no reason** (D8 -- storing it is how the decision gets
    quietly lost), **a slot not in the grid**, **a person the profile does not
    list**, and **a day the rotation says is not theirs** (the cycle being
    silently re-phased). Everything else is kept exactly as the model decided
    it, including choices the audit will warn about.
    """
    if not isinstance(offered, list):
        return []
    known_slots = {(slot["shift_name"], slot["slot_date"]): slot for slot in slots}
    people = _known_people(profile)
    rotation_rows = [
        row for row in availability or []
        if isinstance(row, dict) and row.get("source") in ROTATION_SOURCES
    ]
    assignments, seen = [], set()
    for item in offered:
        row = _usable(item, known_slots, people, rotation_rows)
        if row is None:
            continue
        key = (row["employee"], row["shift"], row["date"])
        if key in seen:
            continue
        seen.add(key)
        assignments.append(row)
    return assignments


def _usable(
    item: Any, known_slots: dict, people: set, rotation_rows: List[dict]
) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    employee, shift = bounded(item.get("employee")), bounded(item.get("shift"))
    date, reason = bounded(item.get("date")), bounded(item.get("reason"))
    if not employee or not shift or not date or not reason:
        return None
    slot = known_slots.get((shift, date))
    if slot is None or (people and employee not in people):
        return None
    placed = {
        "employee": employee, "shift": shift, "date": date,
        "start_time": slot.get("start_time"), "end_time": slot.get("end_time"),
    }
    if any(constraint_conflicts(placed, row) for row in rotation_rows):
        return None
    return {"employee": employee, "shift": shift, "date": date, "reason": reason}


def required_assignments(
    offered: Any, slots: List[dict], profile: dict,
    availability: Optional[List[dict]] = None,
) -> List[dict]:
    """Validate and pin the placements explicitly chosen by the manager."""
    if not offered:
        return []
    known_slots = {(slot["shift_name"], slot["slot_date"]): slot for slot in slots}
    rotation_rows = [row for row in availability or [] if row.get("source") in ROTATION_SOURCES]
    people = {
        bounded(person.get("name"))
        for person in (profile or {}).get("employees") or []
        if isinstance(person, dict)
    }
    required, seen = [], set()
    for item in offered:
        item = item if isinstance(item, dict) else {}
        key = (
            bounded(item.get("employee")),
            bounded(item.get("shift")),
            bounded(item.get("date")),
        )
        if key[0] not in people:
            raise AgentError("העובד שנבחר לשיבוץ החובה אינו קיים בצוות")
        person = next(row for row in profile.get("employees") or [] if bounded(row.get("name")) == key[0])
        if person.get("inactive_from") and key[2] >= person["inactive_from"]:
            raise AgentError("העובד שנבחר סיים את העבודה לפני המשמרת המבוקשת")
        if key[1:] not in known_slots:
            raise AgentError("המשמרת שנבחרה לשיבוץ החובה אינה קיימת בשבוע הזה")
        slot = known_slots[key[1:]]
        placed = dict(employee=key[0], shift=key[1], date=key[2],
                      start_time=slot.get("start_time"), end_time=slot.get("end_time"))
        if any(constraint_conflicts(placed, row) for row in rotation_rows):
            raise AgentError("שיבוץ החובה של %s סותר את זמני הנוכחות של הסבב או התלתון" % key[0])
        if key in seen:
            continue
        seen.add(key)
        required.append({
            "employee": key[0], "shift": key[1], "date": key[2],
            "reason": PINNED_REASON,
        })
    return required


def merge(existing: List[dict], incoming: List[dict]) -> List[dict]:
    """Assignments from a later call added to what earlier ones decided.

    A duplicate is kept as the earlier call placed it. The later call is the
    one working from incomplete information, so the first decision stands and
    nothing silently overwrites a slot the manager may already be looking at.
    """
    seen = {(row["employee"], row["shift"], row["date"]) for row in existing}
    merged = list(existing)
    for row in incoming:
        key = (row["employee"], row["shift"], row["date"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def replace_span(
    existing: List[dict], incoming: List[dict], dates: set
) -> List[dict]:
    """What the roster looks like with these dates re-decided.

    Everything outside the span is kept exactly as it was — a span is
    re-answerable in isolation, which is what makes a failed one retryable
    without disturbing its neighbours.
    """
    return merge(
        [row for row in existing if row.get("date") not in dates], incoming
    )


def committed_for_model(assignments: List[dict]) -> List[dict]:
    """What earlier calls already placed, without the reasons.

    The next call needs to know a slot is taken and who is on it, not to
    re-read a paragraph of justification per row.
    """
    return [
        {"employee": row["employee"], "shift": row["shift"], "date": row["date"]}
        for row in assignments
    ]


def previous_day(assignments: List[dict], day: str) -> List[dict]:
    parsed = parse_date(day)
    if parsed is None:
        return []
    yesterday = (parsed - datetime.timedelta(days=1)).isoformat()
    return committed_for_model(
        [row for row in assignments if row.get("date") == yesterday]
    )
