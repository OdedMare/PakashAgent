"""Profile edits and implied constraints a request may carry."""

from typing import Any, List

from app.bl.changes.schema import (
    MAX_PROFILE_OPERATIONS, PROFILE_ADD_EMPLOYEE, PROFILE_ADD_SHIFT,
    PROFILE_OPERATIONS, PROFILE_UPDATE_EMPLOYEE, PROFILE_UPDATE_SHIFT,
)
from app.bl.changes.values import bounded, date_of


def _names(rows: Any) -> set:
    return {bounded(row.get("name")) for row in rows or [] if isinstance(row, dict)}


def _item(raw: Any) -> dict:
    item = raw if isinstance(raw, dict) else {}
    return {
        "name": bounded(item.get("name")),
        "role": bounded(item.get("role")),
        "eligible_shifts": [
            bounded(value) for value in item.get("eligible_shifts") or []
            if bounded(value)
        ],
        "start_time": bounded(item.get("start_time")),
        "end_time": bounded(item.get("end_time")),
        "headcount": item.get("headcount") or 1,
        "is_on_call": bool(item.get("is_on_call")),
    }


def profile_operations(offered: Any, profile: dict) -> List[dict]:
    """Bound profile edits to the four operations the UI can also perform.

    An add must name something new; an update must target something that
    exists.
    """
    if not isinstance(offered, list):
        return []
    employees = _names((profile or {}).get("employees"))
    shifts = _names((profile or {}).get("shifts"))
    valid = {
        PROFILE_ADD_EMPLOYEE: lambda name, target: name not in employees,
        PROFILE_UPDATE_EMPLOYEE: lambda name, target: target in employees,
        PROFILE_ADD_SHIFT: lambda name, target: name not in shifts,
        PROFILE_UPDATE_SHIFT: lambda name, target: target in shifts,
    }
    result = []
    for raw in offered[:MAX_PROFILE_OPERATIONS]:
        if not isinstance(raw, dict):
            continue
        action, target = bounded(raw.get("action")), bounded(raw.get("target"))
        item = _item(raw.get("item"))
        if action in PROFILE_OPERATIONS and item["name"] \
                and valid[action](item["name"], target):
            result.append({"action": action, "target": target, "item": item})
    return result


def constraints(offered: Any) -> List[dict]:
    """Constraints the request implied, to be remembered rather than
    worked around once.

    "דנה חולה ביום חמישי" is both a change and a fact about Thursday. Storing
    the fact is what stops the next schedule from putting her right back.
    """
    if not isinstance(offered, list):
        return []
    return [
        {
            "employee": bounded(item.get("employee")),
            "date": date_of(item.get("date")),
            "shift": bounded(item.get("shift")),
            "reason": bounded(item.get("reason")),
        }
        for item in offered
        if isinstance(item, dict)
        and bounded(item.get("employee")) and date_of(item.get("date"))
    ]
