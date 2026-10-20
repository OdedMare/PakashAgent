"""What a candidate row does to the structured requests and soft availability.

Pure functions over rows already normalised by `rows.assignment`. Hard
requests block; soft ones cost. A soft availability row (an `is_hard: false`
constraint, dated or expanded from a recurring one) costs one unit when the
candidate falls outside it, through the same `constraint_conflicts` the
audit uses, so "may work only until 15:00, if possible" means one thing
everywhere.

Rest, runs, company and even shares (`min_rest`, `max_consecutive`,
`requires_with`, `balance`) are evaluated in `limits.py`, since they need
shift times and the days before the period.
"""

from typing import List

from app.bl.audit import constraint_conflicts
from app.bl.deterministic_scheduler import limits as kinds
from app.bl.schedule_requests import covers, week_of


def blocks(requests: List[dict], row: dict, current: List[dict], limits=None) -> bool:
    """Whether a hard request forbids `row` given the rows already placed.
    `limits` (`limits.Limits`) is what the rest and run kinds also need."""
    return any(
        request["is_hard"] and _breaks(request, row, current, limits)
        for request in requests
    )


def cost(requests: List[dict], soft_availability: List[dict], row: dict,
         current: List[dict], limits=None) -> float:
    """Soft weight `row` breaks, minus the soft preferences it meets."""
    total = 0.0
    for request in requests:
        if request["is_hard"]:
            continue
        if request["kind"] == "prefer":
            if _concerns(request, row):
                total -= request["weight"]
        elif request["kind"] == "balance":
            total += kinds.balance_cost(request, row, current, limits)
        elif _breaks(request, row, current, limits):
            total += request["weight"]
    total += sum(1.0 for item in soft_availability if constraint_conflicts(row, item))
    return round(total, 6)


def broken(requests: List[dict], soft_availability: List[dict], row: dict,
           current: List[dict], limits=None) -> List[str]:
    """The reasons of every soft wish `row` goes against, for the notes.
    An uneven share is not one: it is a ranking, and every pick but the
    lightest would be reported."""
    reasons = [
        request["reason"] for request in requests
        if not request["is_hard"] and request["kind"] not in ("prefer", "balance")
        and _breaks(request, row, current, limits)
    ]
    reasons.extend(
        item.get("reason") or "אילוץ זמינות רך"
        for item in soft_availability if constraint_conflicts(row, item)
    )
    return reasons


def preferred(requests: List[dict], row: dict) -> List[str]:
    """The reasons of every soft preference `row` meets."""
    return [
        request["reason"] for request in requests
        if request["kind"] == "prefer" and _concerns(request, row)
    ]


def _breaks(request: dict, row: dict, current: List[dict], limits=None) -> bool:
    kind = request["kind"]
    if kind in kinds.LIMIT_KINDS:
        return kinds.breaks(request, row, current, limits)
    if kind == "avoid":
        return _concerns(request, row)
    if kind == "max_count":
        return _concerns(request, row) and _count(request, row, current) + 1 > request["count"]
    if kind == "not_together":
        return _concerns(request, row) and any(
            other["employee"] in request["employees"]
            and other["employee"] != row["employee"]
            and other["shift"] == row["shift"] and other["date"] == row["date"]
            for other in current
        )
    return False


def _concerns(request: dict, row: dict) -> bool:
    return row["employee"] in request["employees"] and covers(
        request, row["shift"], row["date"]
    )


def _count(request: dict, row: dict, current: List[dict]) -> int:
    week = week_of(row["date"]) if request["per"] == "week" else None
    return sum(
        1 for other in current
        if _concerns(request, other)
        and (other["shift"], other["date"]) != (row["shift"], row["date"])
        and (week is None or week_of(other["date"]) == week)
    )


__all__ = ["blocks", "broken", "cost", "preferred"]
