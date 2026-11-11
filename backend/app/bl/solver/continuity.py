"""Continuity: a new week looks like the last two where nothing else decides.

Built from scratch, a week has no reason to put דנה back on the Sunday
morning she held the two weeks before: among schedules equally even and
equally kind to the wishes, the solver picks any, and the team finds a new
pattern every week. The manager asked for the weeks to keep their shape.

So each placement that repeats the person's own pattern — the same shift
on the same weekday as in the last `WEEKS` weeks — earns a small reward,
once for each of those weeks it repeats. The reward is deliberately the
smallest price in the model: below one shift of evenness at the lightest
load weight and below any rest between shifts, so it only picks among
schedules that are otherwise as good. Whoever carried the nights is not
kept on them: the evenness and the eight-week ledger move the nights away
far more strongly than this keeps them.

The pattern is read from the rows before the span (history and the draft
before it), which every solve is already handed. A rotation or closure is
untouched: the reward is only ever on a placement that is legal.

`audit_policy.continuity`: "off", "low" (default) or "high" (twice the
reward, still below one light shift of evenness).
"""

import datetime
from typing import Dict, Set, Tuple

from app.bl.shared import hebrew_weekday
from app.bl.solver.model import Model

WEEKS = 2
REWARD = {"off": 0, "low": 30, "high": 60}


def level(profile: dict) -> str:
    stated = (profile or {}).get("audit_policy")
    value = (stated or {}).get("continuity") if isinstance(stated, dict) else None
    return value if value in REWARD else "low"


def pattern(problem) -> Dict[Tuple[str, str, str], int]:
    """{(person, weekday, shift): weeks of the last `WEEKS` it was worked}."""
    if not problem.dates:
        return {}
    start = datetime.date.fromisoformat(problem.dates[0])
    weeks: Dict[Tuple[str, str, str], Set[int]] = {}
    for row in problem.fixed:
        day = datetime.date.fromisoformat(row["date"])
        days = (start - day).days
        if 0 < days <= WEEKS * 7:
            key = (row["employee"], hebrew_weekday(day), row["shift"])
            weeks.setdefault(key, set()).add((days - 1) // 7)
    return {key: len(found) for key, found in weeks.items()}


def apply_continuity(model: Model) -> None:
    problem = model.problem
    reward = REWARD[level(problem.profile)]
    if not reward:
        return
    worked = pattern(problem)
    if not worked:
        return
    for (name, index), var in sorted(model.x.items()):
        slot = problem.slots[index]
        repeats = worked.get((name, _weekday(slot), slot["shift_name"]), 0)
        if repeats:
            model.price(-reward * repeats, var, kind="continuity")


def matched(problem, chosen) -> Dict[str, int]:
    """How many placed rows repeat their person's pattern, of those whose
    person has one: the metric a build reports."""
    worked = pattern(problem)
    people = {name for name, _, _ in worked}
    rows = [row for row in chosen if row["employee"] in people]
    hits = sum(1 for row in rows if (row["employee"], hebrew_weekday(
        datetime.date.fromisoformat(row["date"])), row["shift"]) in worked)
    return {"continuity_rows": len(rows), "continuity_kept": hits}


def _weekday(slot: dict) -> str:
    return hebrew_weekday(datetime.date.fromisoformat(slot["slot_date"]))
