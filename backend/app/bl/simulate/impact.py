"""Measuring what a hypothetical change would move. Counts, not judgments."""

from typing import Any, Dict, List, Optional

from app.bl.audit import counts_toward_staffing
from app.bl.simulate.hypothetical import iso, text


def _number(value: Any, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def _percent(part: int, whole: int) -> int:
    return 100 if whole <= 0 else int(round(100.0 * part / whole))


def warning_key(warning: dict) -> tuple:
    """What makes two warnings the same warning.

    The message carries running totals, so diffing on it would report a
    warning that merely got worse as a warning that is new.
    """
    return (
        text(warning.get("code")),
        text(warning.get("employee")),
        iso(warning.get("date")),
        text(warning.get("shift")),
    )


def coverage(
    before: List[dict], after: List[dict], slots: List[dict],
    employees: Optional[List[dict]] = None, profile: Optional[dict] = None,
) -> dict:
    """Required against assigned, before and after.

    Capped at each slot's headcount, so three people on a one-person shift is
    one covered place -- not an unstaffed week looking fine because somebody
    was tripled up on Sunday. A seat is filled only by someone who counts
    toward staffing (`audit.counts_toward_staffing`).
    """
    roster = {
        text(person.get("name")): person
        for person in employees or []
        if isinstance(person, dict) and text(person.get("name"))
    }
    required = sum(int(_number(slot.get("headcount"), 1)) for slot in slots)

    def filled(rows: List[dict]) -> int:
        counts: Dict[tuple, int] = {}
        for row in rows:
            if counts_toward_staffing(roster.get(text(row.get("employee"))), profile):
                key = (text(row.get("shift")), iso(row.get("date")))
                counts[key] = counts.get(key, 0) + 1
        return sum(
            min(counts.get((text(slot.get("shift_name")), iso(slot.get("slot_date"))), 0),
                int(_number(slot.get("headcount"), 1)))
            for slot in slots
        )

    was, now = filled(before), filled(after)
    return {
        "required": required,
        "assigned_before": was,
        "assigned_after": now,
        "delta": now - was,
        "percent_before": _percent(was, required),
        "percent_after": _percent(now, required),
    }


def workload(before: dict, after: dict, touched: set) -> List[dict]:
    """Hours per affected person, before and after -- only the people the
    change touches, so two moving names are not buried among twenty."""
    def hours(report: dict) -> Dict[str, float]:
        return {
            text(row.get("employee")): float(row.get("hours") or 0.0)
            for row in report.get("people") or []
        }

    was, now = hours(before), hours(after)
    return [
        {
            "employee": name,
            "hours_before": round(was.get(name, 0.0), 2),
            "hours_after": round(now.get(name, 0.0), 2),
            "delta": round(now.get(name, 0.0) - was.get(name, 0.0), 2),
        }
        for name in sorted(touched)
    ]


def touched(applied: List[dict]) -> set:
    """Everybody whose week the applied operations change.

    Both halves of a swap and the person a `remove` takes off: the one losing
    a shift is as affected as the one gaining it.
    """
    return {
        name for item in applied
        for name in (text(item.get("employee")), text(item.get("with_employee")))
        if name
    }
