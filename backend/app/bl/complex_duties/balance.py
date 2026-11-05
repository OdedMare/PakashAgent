"""The מכלול's duty balance over a span: who stood how much, per soldier,
per משמרת and per kind of duty, and how wide the spread is.

The same weighted count the solver and the fill use (a duty day is
`weight` shifts), beside each soldier's shifts in the span. A report and
nothing more (D3): no quota, no grade.
"""

import datetime
from typing import Dict, List

from app.bl.complex_duties.values import runs_on

_WEEKEND = (4, 5)


def balance(ledger, types: List[dict], first: datetime.date, last: datetime.date) -> dict:
    people: Dict[tuple, dict] = {}
    for soldier in ledger.soldiers:
        if not ledger.serving(soldier):
            continue
        key = (soldier["team_id"], soldier["name"])
        shifts = sum(1 for day in ledger.shift_days.get(key, ()) if first <= day <= last)
        people[key] = {"team_id": soldier["team_id"], "team_name": soldier["team_name"],
                       "employee": soldier["name"], "duties": 0, "duty_load": 0,
                       "weekend_duties": 0, "recorded": 0, "shifts": shifts}
    kinds = {row["id"]: {"duty_type_id": row["id"], "duty": row["name"], "filled": 0,
                         "required": _required(row, first, last), "weight": row["weight"]}
             for row in types}
    for row in ledger.duties:
        day = _day(row["duty_date"])
        if day is None or not first <= day <= last:
            continue
        person = people.get((row["team_id"], row["employee"]))
        if person is not None:
            person["duties"] += 1
            person["duty_load"] += max(0, row.get("weight") or 0)
            person["weekend_duties"] += day.weekday() in _WEEKEND
            person["recorded"] += not row.get("blocks", True)
        kind = kinds.get(row["duty_type_id"])
        if kind is not None and row.get("blocks", True):
            kind["filled"] += 1
    rows = sorted(people.values(), key=lambda item: (
        -item["duty_load"], -(item["duty_load"] + item["shifts"]), item["team_name"], item["employee"]))
    for item in rows:
        item["load"] = item["duty_load"] + item["shifts"]
    loads = [item["duty_load"] for item in rows]
    return {
        "start": first.isoformat(), "end": last.isoformat(),
        "people": rows,
        "teams": _teams(rows),
        "types": [kind for kind in kinds.values() if kind["required"] or kind["filled"]],
        "spread": {"most": max(loads, default=0), "least": min(loads, default=0),
                   "gap": (max(loads) - min(loads)) if loads else 0},
    }


def _teams(rows: List[dict]) -> List[dict]:
    teams: Dict[str, dict] = {}
    for item in rows:
        team = teams.setdefault(item["team_id"], {"team_id": item["team_id"],
                                                  "team_name": item["team_name"],
                                                  "soldiers": 0, "duties": 0, "duty_load": 0})
        team["soldiers"] += 1
        team["duties"] += item["duties"]
        team["duty_load"] += item["duty_load"]
    for team in teams.values():
        team["average"] = round(team["duty_load"] / team["soldiers"], 2) if team["soldiers"] else 0
    return sorted(teams.values(), key=lambda team: team["team_name"])


def _required(duty_type: dict, first: datetime.date, last: datetime.date) -> int:
    """Seats the kind asked for over the span, on the days it runs, from the
    day it was created -- a kitchen added this week did not ask for seven
    weeks of seats before it. A retired kind asks for none."""
    if not duty_type.get("active", True):
        return 0
    created = _day(duty_type.get("created_at"))
    day, seats = max(first, created) if created else first, 0
    while day <= last:
        seats += duty_type["seats"] if runs_on(duty_type, day) else 0
        day += datetime.timedelta(days=1)
    return seats


def _day(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None
