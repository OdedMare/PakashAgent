"""The fairness ledger: load carried in the weeks before the last two.

The rows of the last `LOOKBACK_DAYS` (14) are fixed rows and count in
every rule — rest, runs of days, the week — and in the load. Who carried
the nights a month ago is not visible there, so a soldier who took more
than their share in weeks three to eight was asked for an even share again
as soon as two weeks had passed. The ledger carries that older load into
the evenness, and nowhere else: rest and runs of days do not reach back
that far, and a row of the ledger is never a fixed row.

- **The window** is `audit_policy.fairness_lookback_weeks` weeks before
  the span (default 8, at most `MAX_WEEKS`; 0 turns the ledger off). Its
  first two weeks are the fixed rows; the ledger is the rest.
- **Decay.** A shift in the four weeks before the span counts whole; an
  older one counts half (`OLD_SHARE`). An excess two months ago still
  evens out, but less than one last month.
- **Absent weeks are filled at the team's own rate.** A soldier first seen
  three weeks ago (a newcomer, or back from a long absence) did not refuse
  the weeks before that: for each week of the window before their first
  row they are credited what the team carried per person that week, on
  average. Only a week the team had a schedule in is filled (a shift row,
  not only a מכלול duty): with no history there is nobody to be new
  against. Without it a newcomer was owed every shift the others carried
  over two months and was handed all of them at once.

Counted in the measure the evenness uses (`fairness.load_units` for
shifts, one night per night), so the ledger and the grid add up.
"""

import datetime
from typing import Callable, Dict, List, Set

from app.bl.audit.values import number, text

DEFAULT_WEEKS = 8
MAX_WEEKS = 12
# Weeks before the span that count whole; older ones count `OLD_SHARE`.
FULL_WEEKS = 4
OLD_SHARE = 0.5


def lookback_weeks(profile: dict) -> int:
    """The window in weeks, from `audit_policy.fairness_lookback_weeks`."""
    stated = (profile or {}).get("audit_policy")
    stated = stated if isinstance(stated, dict) else {}
    weeks = int(number(stated.get("fairness_lookback_weeks"), DEFAULT_WEEKS))
    return max(0, min(MAX_WEEKS, weeks))


def share(age_days: int) -> float:
    """What a row `age_days` before the span counts for."""
    return 1.0 if age_days <= FULL_WEEKS * 7 else OLD_SHARE


def carried(rows: List[dict], first_seen: Dict[str, int], active: Set[int],
            names: List[str], weeks: int, measure: Callable[[dict], int]) -> Dict[str, int]:
    """Each person's older load in the measure's units, plus what the team
    carried per person in the weeks they were not there.

    `rows` carry their `age` in days before the span; a `recent` one is a
    fixed row, already counted by the evenness itself, and only sets the
    team's rate. `first_seen` is how many days before the span each
    person's first row in the window falls (absent: never seen); `active`
    the weeks the team had a schedule at all, the only ones filled. `names`
    are the people evened."""
    if not weeks or not names:
        return {}
    load = {name: 0.0 for name in names}
    total = 0.0
    for row in rows:
        if row["employee"] in load:
            value = share(row["age"]) * measure(row)
            total += value
            load[row["employee"]] += 0.0 if row.get("recent") else value
    all_weeks = [week for week in range(1, weeks + 1) if week in active]
    present = {name: [week for week in all_weeks if _present(first_seen, name, week)]
               for name in names}
    weight = sum(share(week * 7) for weeks_in in present.values() for week in weeks_in)
    rate = total / weight if weight else 0.0
    for name in names:
        missing = [week for week in all_weeks if week not in present[name]]
        load[name] += sum(rate * share(week * 7) for week in missing)
    return {name: int(round(value)) for name, value in load.items() if round(value) > 0}


def _present(first_seen: Dict[str, int], name: str, week: int) -> bool:
    """On the team during `week` (1 = the week right before the span)."""
    return first_seen.get(name, 0) > (week - 1) * 7


def age(day: str, start: datetime.date) -> int:
    """Days from `day` to the span's first date."""
    return (start - datetime.date.fromisoformat(day)).days


def window(history: List[dict], fixed: List[dict], duties: List[dict], start: datetime.date,
           weeks: int, recent_days: int, timed: Callable[[dict], dict]) -> tuple:
    """The ledger's rows, who was first seen when and which weeks the team
    had a schedule in, from the rows handed
    to a solve: `history` (earlier periods), `fixed` (the draft around the
    span and the last two weeks) and `duties` (מכלול duty days, counted as
    a shift of their weight that is not a night). A fixed row before the
    span is marked `recent`: it sets the team's rate and is not counted
    again. A duty day inside the fixed rows' days is `Problem.duty_load`'s,
    and likewise only sets the rate."""
    limit, rows, first_seen, active = weeks * 7, [], {}, set()
    taken = {(row["employee"], row["shift"], row["date"]) for row in fixed}

    def seen(name: str, days: int) -> bool:
        if not 0 < days <= limit:
            return False
        first_seen[name] = max(first_seen.get(name, 0), days)
        return days > recent_days

    def scheduled(days: int) -> None:
        if 0 < days <= limit:
            active.add((days - 1) // 7 + 1)

    for row in history:
        days = age(row["date"], start)
        scheduled(days)
        if seen(row["employee"], days) and (row["employee"], row["shift"], row["date"]) not in taken:
            rows.append(dict(timed(row), age=days))
    for row in fixed:
        days = age(row["date"], start)
        scheduled(days)
        if 0 < days <= limit:
            seen(row["employee"], days)
            rows.append(dict(row, age=days, recent=True))
    for (name, day), weight in _duty_days(duties).items():
        days = age(day, start)
        if 0 < days <= limit:
            rows.append({"employee": name, "age": days, "night": False, "load": float(weight),
                         "recent": not seen(name, days)})
    return rows, first_seen, active


def _duty_days(duties: List[dict]) -> Dict[tuple, int]:
    """`team_complex_duties` rows as {(person, date): weight}, one a day,
    read the way `Problem._duty_load` reads them."""
    days = {}
    for row in duties or []:
        if not isinstance(row, dict):
            continue
        day = str(row.get("duty_date") or row.get("date") or "")[:10]
        weight = row.get("weight", 1)
        weight = weight if isinstance(weight, int) and not isinstance(weight, bool) else 1
        if text(row.get("employee")) and len(day) == 10:
            days.setdefault((text(row.get("employee")), day), max(0, weight))
    return days
