"""The rotation per date (for the board) and per weekend (for the model)."""

import datetime
from typing import Dict, List

from app.bl.rotation.closures import closure_days, handover_shifts, window_rule
from app.bl.rotation.cycle import cycle, group_for_saturday
from app.bl.rotation.vocabulary import (
    CLOSURE_LEAD_DAYS, GROUPED_PATTERNS, exit_pattern, groups_for, label,
    people, saturday_of, text,
)


class _DateEntry:
    """Every claim landing on one date, accumulated across the roster."""

    def __init__(self, date: str, weekend: str):
        self.date, self.weekend = date, weekend
        # Keyed by cycle: a חמשושים א and a round א are the same א.
        self.closing_groups: Dict[str, str] = {}
        self.employees: List[str] = []
        self.shifts: List[str] = []
        # A date is a handover only while *every* closure landing on it is
        # one; otherwise the fuller closure would be cut short.
        self.until_handover = True
        self.restricted_shifts = True

    def add(self, name: str, row: dict) -> None:
        if row["cycle"] and row["group"]:
            self.closing_groups[row["cycle"]] = row["group"]
        if name and name not in self.employees:
            self.employees.append(name)
        self.until_handover = self.until_handover and row["until_handover"]
        if not (row["until_handover"] or row.get("restricted_shifts")):
            self.restricted_shifts, self.shifts = False, []
        elif self.restricted_shifts:
            self.shifts.extend(s for s in row["shifts"] if s not in self.shifts)

    def to_dict(self) -> dict:
        groups = [
            {"pattern": cycle, "group": group, "label": label(cycle, group)}
            for cycle, group in sorted(self.closing_groups.items())
        ]
        return {
            "date": self.date,
            "weekend": self.weekend,
            "groups": groups,
            "label": " ו".join(item["label"] for item in groups),
            "employees": sorted(self.employees),
            # Empty means the whole date; named shifts mean until the handover.
            "shifts": sorted(self.shifts),
            "until_handover": bool(self.until_handover),
        }


def by_date(profile: dict, start: datetime.date, end: datetime.date) -> Dict[str, dict]:
    """Every closure *day* in the period: whose it is, and who is held on it.

    A date with no entry is an ordinary working day and belongs to nobody --
    the absence is the answer. Empty for a workplace that never anchored a
    cycle.
    """
    if start > end:
        return {}
    entries: Dict[str, _DateEntry] = {}
    roster = people(profile)

    # A cycle still has an owner on a weekend when that group currently has
    # nobody in the roster. Seed every used cycle before adding its people so
    # the board does not skip, for example, triplet A between triplet C and B.
    active_cycles = set()
    for person in roster:
        pattern = exit_pattern(profile, person)
        if text(person.get("rotation_group")) and pattern in GROUPED_PATTERNS:
            active_cycles.add(pattern)
    for pattern in sorted(active_cycles):
        for group in groups_for(pattern) or ():
            for row in closure_days(
                profile,
                {"exit_pattern": pattern, "rotation_group": group},
                start,
                end,
            ):
                entry = entries.setdefault(
                    row["date"], _DateEntry(row["date"], row["weekend"])
                )
                entry.add("", row)

    for person in roster:
        name = text(person.get("name"))
        for row in closure_days(profile, person, start, end):
            entry = entries.setdefault(row["date"], _DateEntry(row["date"], row["weekend"]))
            entry.add(name, row)
    return {date: entry.to_dict() for date, entry in entries.items()}


def schedule_for_model(profile: dict, start: datetime.date, end: datetime.date) -> List[dict]:
    """The period's closures, per weekend, as the model should read them.

    A weekend carries `closing_groups` rather than one group, because a unit
    running both structures has a round group and a triplet group in on the
    same weekend.
    """
    days = by_date(profile, start, end)
    weekends: Dict[str, dict] = {}
    for date in sorted(days):
        day = days[date]
        weekend = weekends.setdefault(day["weekend"], {
            "weekend": day["weekend"], "closing_groups": {}, "days": [],
        })
        for item in day["groups"]:
            weekend["closing_groups"][item["pattern"]] = item["group"]
        weekend["days"].append({"date": date, "employees": day["employees"]})
    return [
        {
            "weekend": weekend["weekend"],
            "closing_groups": [
                {"pattern": pattern, "group": group}
                for pattern, group in sorted(weekend["closing_groups"].items())
            ],
            "days": weekend["days"],
        }
        for weekend in sorted(weekends.values(), key=lambda item: item["weekend"])
    ]


def weekend_preview(
    profile: dict, pattern: str, start: datetime.date, weeks: int
) -> List[dict]:
    """The next `weeks` closures of one cycle, as the setup screen shows them.

    Read by the same lookups the scheduler uses -- `group_for_saturday` and
    `window_rule` -- so the preview cannot disagree with a build. `kind` says
    where the hours came from: `default` (Thursday to the Sunday handover),
    `regular` (the cycle's own hours) or `exception` (a dated row). Empty for
    a cycle with no anchor.
    """
    state = cycle(profile, pattern)
    if state is None:
        return []
    handover = handover_shifts(profile)
    saturday = saturday_of(start)
    result = []
    for _ in range(max(0, weeks)):
        group = group_for_saturday(state, saturday)
        row = window_rule(profile, pattern, group, saturday)
        item = {"saturday": saturday.isoformat(), "group": group,
                "label": label(pattern, group)}
        if row is None:
            first = saturday - datetime.timedelta(days=CLOSURE_LEAD_DAYS[pattern])
            item.update(kind="default", start_date=first.isoformat(), start_time="",
                        end_date=(saturday + datetime.timedelta(days=1 if handover else 0)).isoformat(),
                        end_time="", handover_shifts=list(handover))
        else:
            item.update(
                kind="exception" if row.get("starts_on") or row.get("ends_on") else "regular",
                start_date=(saturday + datetime.timedelta(days=row["start_day"])).isoformat(),
                start_time=row["start_time"],
                end_date=(saturday + datetime.timedelta(days=row["end_day"])).isoformat(),
                end_time=row["end_time"], handover_shifts=[],
                note=text(row.get("note")),
            )
        result.append(item)
        saturday += datetime.timedelta(days=7)
    return result
