"""Which rows a build must keep: the manager's pins, and what each span writes.

Pure functions over a stored schedule. The board stays writable while a job
runs, so a shift placed by hand on a date not yet generated becomes a pin the
agent fills around, and the checkpoint keeps it with the manager's own source
whether or not the model repeats it.
"""

from typing import Iterable, List

from app.bl.schedule_service.constants import PINNED_REASON
from app.bl.schedule_service.rows import employees, iso, text
from app.common.errors import AgentError
from app.dal.repository.schedules import ASSIGNED_BY_AGENT, ASSIGNED_BY_MANAGER


def required_rows(
    required: List[dict], slots: List[dict], profile: dict
) -> List[dict]:
    """Validate manager-pinned rows against the roster and the stored grid."""
    people = {
        text(row.get("name")) for row in employees(profile)
        if text(row.get("name"))
    }
    by_key = {
        (text(row.get("shift_name")), iso(row.get("slot_date"))): row
        for row in slots
    }
    rows, seen = [], set()
    for item in required:
        employee = text(item.get("employee"))
        key = (employee, text(item.get("shift")), iso(item.get("date")))
        if employee not in people:
            raise AgentError("העובד שנבחר לשיבוץ החובה אינו קיים בצוות")
        slot = by_key.get(key[1:])
        if slot is None:
            raise AgentError("המשמרת שנבחרה לשיבוץ החובה אינה קיימת בטווח הזה")
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "slot_id": slot["id"],
            "employee": employee,
            "reason": PINNED_REASON,
            "source": ASSIGNED_BY_MANAGER,
        })
    return rows


def model_assignment(row: dict) -> dict:
    """A stored row as the model is shown it in `already_scheduled`."""
    return {
        "employee": text(row.get("employee")),
        "shift": text(row.get("shift")),
        "date": iso(row.get("date")),
        "reason": text(row.get("reason")) or "שיבוץ קיים בסידור",
    }


def manager_rows_in(schedule: dict, dates: Iterable[str]) -> List[dict]:
    """What the manager placed by hand anywhere in a span of a running job."""
    wanted = set(dates)
    return [
        {
            "employee": text(row.get("employee")),
            "shift": text(row.get("shift")),
            "date": iso(row.get("date")),
        }
        for row in schedule.get("assignments") or []
        if iso(row.get("date")) in wanted
        and row.get("source") == ASSIGNED_BY_MANAGER
        and text(row.get("employee")) and text(row.get("shift"))
    ]


def merged_required_rows(
    pinned: List[dict], manual: List[dict]
) -> List[dict]:
    """The pins for one span, without repeating a row named by both."""
    rows, seen = [], set()
    for row in list(pinned) + list(manual):
        key = (
            text(row.get("employee")),
            text(row.get("shift")),
            iso(row.get("date")),
        )
        if not key[0] or key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def span_pins(schedule: dict, required: List[dict], dates: List[str]) -> List[dict]:
    """What the job pinned on these dates, plus what was placed since."""
    wanted = set(dates)
    return merged_required_rows(
        [row for row in required or [] if iso(row.get("date")) in wanted],
        manager_rows_in(schedule, wanted),
    )


def persisted_rows(
    schedule: dict, generated: List[dict], dates: Iterable[str]
) -> List[dict]:
    """Replace the generated dates while preserving every other checkpoint.

    Manager-placed rows on those dates are kept rather than replaced. They
    went in as pins the model was told to work around, so dropping the ones
    it failed to repeat would silently undo a manager's own click.

    Returns the **whole period's** rows, each carrying its date. Both writers
    read what they need: `replace_span_assignments` filters to the span it is
    deleting, and the whole-period fallback takes the list as it stands.
    """
    wanted = set(dates)
    stored = schedule.get("assignments") or []
    rows = [_kept_row(row) for row in stored if _survives(row, wanted)]
    pinned = {
        _key(row) for row in stored
        if iso(row.get("date")) in wanted
        and row.get("source") == ASSIGNED_BY_MANAGER
    }
    sources = {_key(row): row.get("source") or ASSIGNED_BY_AGENT for row in stored}
    slot_ids = {
        (text(slot.get("shift_name")), iso(slot.get("slot_date"))): slot["id"]
        for slot in schedule.get("slots") or []
    }
    for item in generated:
        slot_id = slot_ids.get((item.get("shift"), iso(item.get("date"))))
        key = _key(item)
        # A pinned key was already carried over with the manager's own source
        # and reason; adding it again would be a duplicate row for one slot.
        if slot_id is None or key in pinned:
            continue
        rows.append({
            "slot_id": slot_id,
            "employee": item["employee"],
            "reason": item["reason"],
            "source": sources.get(key, ASSIGNED_BY_AGENT),
            "date": iso(item.get("date")),
        })
    return rows


def _survives(row: dict, wanted: set) -> bool:
    return (
        iso(row.get("date")) not in wanted
        or row.get("source") == ASSIGNED_BY_MANAGER
    )


def _kept_row(row: dict) -> dict:
    return {
        "slot_id": row["slot_id"],
        "employee": row["employee"],
        "reason": row["reason"],
        "source": row.get("source") or ASSIGNED_BY_AGENT,
        "date": iso(row.get("date")),
    }


def _key(row: dict) -> tuple:
    return (row.get("employee"), text(row.get("shift")), iso(row.get("date")))
