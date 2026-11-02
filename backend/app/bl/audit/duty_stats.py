"""מכלול duties in the stats panel: how many, of which kind, and the load.

A duty day is load the soldier carried outside the team's grid, counted in
shifts by its type's `weight` -- the same figure the solver evens out
(`solver/problem._duty_load`), so the panel and the build agree on who is
carrying more. A report like the rest of `shift_stats`: nothing here is a
quota (D3). With no duties every figure is zero and `load` is `shifts`.
"""

import datetime
from typing import Dict, List, Optional

from app.bl.audit.values import text

# Friday and Saturday, `date.weekday()`: the duties counted apart, as nights
# are beside shifts.
_WEEKEND = (4, 5)


def add_duties(stats: dict, duties: Optional[List[dict]], employee: str = "") -> dict:
    """`stats` with each person's duties beside their shifts, re-ordered by
    the whole load. `duties` are `team_complex_duties` rows."""
    rows = [row for row in duties or [] if isinstance(row, dict)
            and (not employee or text(row.get("employee")) == employee)]
    people: Dict[str, dict] = {}
    kinds: Dict[str, dict] = {}
    for row in rows:
        name, kind = text(row.get("employee")), text(row.get("duty_type"))
        weight = _weight(row)
        weekend = _weekday(row.get("duty_date")) in _WEEKEND
        person = people.setdefault(name, {"duties": 0, "duty_load": 0, "weekend_duties": 0})
        person["duties"] += 1
        person["duty_load"] += weight
        person["weekend_duties"] += weekend
        entry = kinds.setdefault(kind, {"duty": kind, "count": 0, "load": 0, "weight": weight})
        entry["count"] += 1
        entry["load"] += weight
    for item in stats.get("by_employee") or []:
        item.update(people.get(item["employee"], {"duties": 0, "duty_load": 0,
                                                    "weekend_duties": 0}))
        item["load"] = item["shifts"] + item["duty_load"]
    stats["by_employee"] = sorted(
        stats.get("by_employee") or [],
        key=lambda item: (-item["load"], -item["shifts"], -item["hours"], item["employee"]),
    )
    stats["total_duties"] = len(rows)
    stats["total_duty_load"] = sum(_weight(row) for row in rows)
    stats["by_duty"] = sorted(kinds.values(), key=lambda item: (-item["count"], item["duty"]))
    return stats


def _weight(row: dict) -> int:
    weight = row.get("weight", 1)
    return max(0, weight) if isinstance(weight, int) and not isinstance(weight, bool) else 1


def _weekday(value) -> Optional[int]:
    if isinstance(value, datetime.date):
        return value.weekday()
    try:
        return datetime.date.fromisoformat(str(value or "")[:10]).weekday()
    except ValueError:
        return None
