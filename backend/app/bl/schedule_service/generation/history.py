"""Earlier periods' assignments, read once per build for the fairness tally --
and the team's מכלול duties around a build, which count as load carried."""

import datetime
import time
from threading import Lock
from typing import List

from app.bl.shift_sequences import rules_for
from app.bl.roster_limits import monthly_officer_limit
from app.bl.schedule_service.constants import (
    HISTORY_CACHE_ENTRIES,
    HISTORY_CACHE_SECONDS,
    HISTORY_ROW_LIMIT,
)
from app.bl.schedule_service.rows import iso
from app.bl.solver.ledger import MAX_WEEKS

# The widest window any build looks back over: the fairness ledger's.
LEDGER_DAYS = MAX_WEEKS * 7


class AssignmentHistory:
    """Assignments from earlier periods, briefly cached.

    The scheduler needs to know who has been carrying the nights, and that is
    not visible inside the period being built. It reads only periods starting
    *before* the one being generated, so the answer is identical for every
    span of a run — and it was recomputed for each one, scanning and joining
    the team's whole schedule history per generated date. The window is short
    enough that a period imported or edited alongside a build is picked up on
    the next read.
    """

    def __init__(self, repository, clock=time.monotonic):
        self._repository = repository
        self._clock = clock
        # (team, before) -> (expires_at, rows).
        self._cache = {}
        self._lock = Lock()

    def before(self, team_id: str, before: str) -> List[dict]:
        key = (team_id, before)
        now = self._clock()
        with self._lock:
            cached = self._cache.get(key)
            if cached and cached[0] > now:
                return list(cached[1])
        rows = self._read(team_id, before)
        with self._lock:
            # Bounded so a long-lived process serving many teams cannot grow
            # this without limit; dropping the oldest costs one re-read.
            if len(self._cache) > HISTORY_CACHE_ENTRIES:
                self._cache.clear()
            self._cache[key] = (now + HISTORY_CACHE_SECONDS, rows)
        return list(rows)

    def for_build(self, team_id, profile, starts_on, ends_on):
        cap = monthly_officer_limit(profile)
        reach = max((max(1, rule.count - 1) for rule in rules_for(profile)
                     if rule.kind in ("run", "after")), default=0)
        if cap is None and not reach:
            return self.before(team_id, starts_on)
        # A month may already have shifts on either side of a rebuilt week.
        # Read fresh so a manual edit can immediately spend or free the quota.
        rows = self._read(team_id, starts_on)
        for period in self._repository.list_schedules(team_id):
            first = iso(period["starts_on"])
            nearby = first <= _days_before(ends_on, -reach)
            same_month = cap is not None and first[:7] <= ends_on[:7]
            if first <= starts_on or not (nearby or same_month):
                continue
            rows.extend(dict(employee=row["employee"], shift=row["shift"], date=iso(row["date"]))
                        for row in self._repository.assignments(period["id"], team_id)
                        if iso(row["date"]) > ends_on)
        return rows

    def _read(self, team_id: str, before: str) -> List[dict]:
        """Every row of the earlier periods inside the fairness ledger's
        widest window (`solver/ledger.MAX_WEEKS`), newest period first. Bounded
        by date, not by a count of rows: a count stopped a team of thirty
        about a month back, short of the eight weeks the ledger evens over.
        `HISTORY_ROW_LIMIT` is only a guard against a runaway history."""
        rows: List[dict] = []
        cutoff = _days_before(before, LEDGER_DAYS)
        for period in self._repository.list_schedules(team_id):
            if iso(period["starts_on"]) >= before:
                continue
            if cutoff and iso(period.get("ends_on")) and iso(period["ends_on"]) < cutoff:
                break
            rows.extend(
                {
                    "employee": row["employee"],
                    "shift": row["shift"],
                    "date": iso(row["date"]),
                }
                for row in self._repository.assignments(period["id"], team_id)
                if not cutoff or iso(row["date"]) >= cutoff
            )
            if len(rows) > HISTORY_ROW_LIMIT:
                break
        return rows

    def duties(self, team_id: str, starts_on: str, ends_on: str) -> List[dict]:
        """The team's מכלול duties a build counts as load (blocking or only
        recorded): from the fairness ledger's widest window before
        `starts_on` through `ends_on`. Empty for a team outside a מכלול, or a repository that
        holds none. Not cached: a duty set a moment ago must count."""
        reader = getattr(self._repository, "team_complex_duties", None)
        if reader is None or not starts_on or not ends_on:
            return []
        try:
            first = datetime.date.fromisoformat(iso(starts_on)) - datetime.timedelta(
                days=LEDGER_DAYS)
        except ValueError:
            return []
        return [
            {"employee": row["employee"], "duty_date": iso(row["duty_date"]),
             "weight": row.get("weight", 1)}
            for row in reader(team_id, first.isoformat(), iso(ends_on))
        ]


def _days_before(day: str, days: int) -> str:
    try:
        return (datetime.date.fromisoformat(iso(day)) - datetime.timedelta(days=days)).isoformat()
    except (TypeError, ValueError):
        return ""
