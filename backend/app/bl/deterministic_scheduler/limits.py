"""The request kinds that need more than the row itself (`schedule_requests`).

`min_rest` needs shift times, `max_consecutive` and `min_rest` need the days
before the period, `requires_with` needs who is already on the slot, and
`balance` needs everyone's count so far. `Limits` carries the first two for
one date; the rest is the rows placed so far, as for the older kinds.
"""

import datetime
from typing import Dict, List

from app.bl.audit.roster import ends_at, index_shifts, row as timed_row, starts_at
from app.bl.audit.checks.people import runs
from app.bl.schedule_requests import concerns, covers

LIMIT_KINDS = ("min_rest", "max_consecutive", "requires_with")
# How far back a run or a short rest is looked for before the period.
LOOKBACK_DAYS = 14


class Limits:
    def __init__(self, shifts: List[dict], recent: List[dict], people=()):
        self.index = index_shifts(shifts or [])
        self.recent = list(recent or [])
        self.people = list(people)


def breaks(request: dict, row: dict, current: List[dict], limits: "Limits") -> bool:
    """Whether `row` goes against one of the `LIMIT_KINDS`."""
    kind = request["kind"]
    # A rest is between two shifts; narrowed to nights, it is any rest
    # touching a night, so the candidate's own shift is not the test.
    scope = dict(request, shifts=[]) if kind == "min_rest" else request
    if not concerns(request, row["employee"]) or not covers(scope, row["shift"], row["date"]):
        return False
    if kind == "requires_with":
        return not any(other["employee"] in request["partners"] and other["shift"] == row["shift"]
                       and other["date"] == row["date"] for other in current)
    if limits is None:
        return False
    mine = [other for other in limits.recent + current if other["employee"] == row["employee"]
            and (other["shift"], other["date"]) != (row["shift"], row["date"])]
    if kind == "max_consecutive":
        return _run_through(row, mine, request) > request["count"]
    return _short_rest(row, mine, request, limits.index)


def balance_cost(request: dict, row: dict, current: List[dict], limits: "Limits") -> float:
    """How far ahead of the least loaded of its group `row` would put its person."""
    if not concerns(request, row["employee"]) or not covers(request, row["shift"], row["date"]):
        return 0.0
    group = request["employees"] or (limits.people if limits else [])
    counts: Dict[str, int] = {name: 0 for name in group}
    for other in current:
        if other["employee"] in counts and covers(request, other["shift"], other["date"]):
            counts[other["employee"]] += 1
    if row["employee"] not in counts:
        return 0.0
    return request["weight"] * (counts[row["employee"]] - min(counts.values()))


def recent(rows: List[dict], target: datetime.date) -> List[dict]:
    """The history rows from the days a rest or a run could still reach."""
    return [row for row in rows if _day(row["date"]) is not None
            and 0 < (target - _day(row["date"])).days <= LOOKBACK_DAYS]


def _run_through(row: dict, mine: List[dict], request: dict) -> int:
    days = {_day(other["date"]) for other in mine if covers(request, other["shift"], other["date"])}
    target = _day(row["date"])
    days.add(target)
    for start, length in runs(sorted(day for day in days if day is not None)):
        if start <= target < start + datetime.timedelta(days=length):
            return length
    return 1


def _short_rest(row: dict, mine: List[dict], request: dict, index: Dict[str, dict]) -> bool:
    candidate = timed_row(row, index)
    if not _timed(candidate):
        return False
    for other in mine:
        if request["shifts"] and row["shift"] not in request["shifts"] \
                and other["shift"] not in request["shifts"]:
            continue
        previous = timed_row(other, index)
        if not _timed(previous):
            continue
        earlier, later = sorted((previous, candidate), key=starts_at)
        if (starts_at(later) - ends_at(earlier)).total_seconds() / 3600.0 < request["count"]:
            return True
    return False


def _timed(item) -> bool:
    return bool(item) and None not in (item.get("day"), item.get("start"), item.get("end"))


def _day(value: str):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


__all__ = ["LIMIT_KINDS", "LOOKBACK_DAYS", "Limits", "balance_cost", "breaks", "recent"]
