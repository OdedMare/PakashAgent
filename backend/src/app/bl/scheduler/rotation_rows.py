"""The rotation and closure cycles, expressed as hard unavailability rows.

Derived from `bl/rotation.py` rather than asked of the model, for the reason
`audit.py` is code: which group closes on 12/09 is arithmetic
([D3](../../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
"""

import datetime
from typing import Dict, List, Optional

from app.bl import rotation as rotation_cycle
from app.bl.audit import constraint_conflicts
from app.bl.hebrew_calendar import weekday_key
from app.bl.scheduler.slots import build_slots
from app.bl.scheduler.values import bounded

# Availability rows derived from the rotation itself rather than read from the
# manager's constraints. An assignment contradicting one puts somebody in on a
# weekend that is not theirs, so both sources are refused on every generation
# path -- a gate in only one route is a gate the other walks around.
ROTATION_SOURCES = frozenset({"rotation", "closure"})

_ROUND_GROUPS = ("א", "ב")
_ROTATING_PATTERNS = ("round", "triplet", "hamshushim", "shushim")


def overridden(keys: set, employee: str, date: str, shift: str) -> bool:
    """Whether an explicit dated row already speaks for this occurrence."""
    return (employee, date, shift) in keys or (employee, date, "") in keys


def _blocked_row(employee: str, slot: dict, reason: str, **extra) -> dict:
    row = {
        "employee": employee,
        "date": slot["slot_date"],
        "shift": slot["shift_name"],
        "available": False,
        "start_time": "",
        "end_time": "",
        "is_hard": True,
        "reason": reason,
    }
    row.update(extra)
    return row


# -- round rotation (A/B complement) -----------------------------------------


def rotation_availability(
    profile: dict, start: datetime.date, end: datetime.date, keys: set,
) -> List[dict]:
    """Expand Rotation A once; Rotation B is its exact slot complement."""
    workplace = (profile or {}).get("workplace") or {}
    rules = [
        rule for rule in workplace.get("rotation_a_unavailability") or []
        if isinstance(rule, dict)
    ]
    if not rules:
        return []
    people = _round_people(profile, workplace)
    result = []
    for slot in build_slots(profile, start.isoformat(), end.isoformat()):
        unavailable_a = _rotation_a_blocks(slot, rules)
        for employee, group in people:
            unavailable = unavailable_a if group == "א" else not unavailable_a
            if not unavailable or overridden(
                keys, employee, slot["slot_date"], slot["shift_name"]
            ):
                continue
            result.append(_blocked_row(
                employee, slot, "סבב %s אינו זמין במועד זה" % group,
                source="rotation",
                rotation_group=group,
                derived_from="rotation_a_unavailability",
            ))
    return result


def _round_people(profile: dict, workplace: dict) -> List[tuple]:
    people = []
    for person in (profile or {}).get("employees") or []:
        if not isinstance(person, dict):
            continue
        pattern = bounded(person.get("exit_pattern")) or bounded(
            workplace.get("rotation_mode")
        ) or "round"
        group = bounded(person.get("rotation_group"))
        name = bounded(person.get("name"))
        if pattern == "round" and group in _ROUND_GROUPS and name:
            people.append((name, group))
    return people


def _rotation_a_blocks(slot: dict, rules: List[dict]) -> bool:
    weekday = weekday_key(slot.get("weekday"))
    for rule in rules:
        days = {weekday_key(item) for item in rule.get("days") or [] if weekday_key(item)}
        if days and weekday not in days:
            continue
        shifts = {bounded(item) for item in rule.get("shifts") or [] if bounded(item)}
        if shifts and slot.get("shift_name") not in shifts:
            continue
        occurrence = {
            "employee": "rotation-a", "date": slot.get("slot_date"),
            "shift": slot.get("shift_name"),
        }
        assignment = dict(
            occurrence,
            start_time=slot.get("start_time"), end_time=slot.get("end_time"),
        )
        constraint = dict(
            occurrence, available=False,
            start_time=rule.get("start_time"), end_time=rule.get("end_time"),
        )
        if constraint_conflicts(assignment, constraint):
            return True
    return False


# -- closures ----------------------------------------------------------------


class ClosureHoldings:
    """Who holds each closure date, under which cycle, and for which shifts.

    A person on a rotation the profile never anchored contributes nothing, so
    their days simply stay unconstrained. `covered` is absent for a whole-day
    date and a set of shifts for the Sunday handover; a date carrying both
    kinds is a whole-day date, or the fuller closure would be cut short.
    """

    def __init__(self, profile: dict, people: List[dict], start, end):
        self.holders: Dict[str, set] = {}
        self.cycles: Dict[str, set] = {}
        self.owners: Dict[str, set] = {}
        self.covered: Dict[str, Optional[set]] = {}
        self.on_rotation: Dict[str, bool] = {}
        for person in people:
            name = bounded(person.get("name"))
            rows = rotation_cycle.closure_days(profile, person, start, end)
            self.on_rotation[name] = bool(rows) or _on_rotation(profile, person)
            for row in rows:
                self._hold(name, row)

    def _hold(self, name: str, row: dict) -> None:
        date = row["date"]
        self.holders.setdefault(date, set()).add(name)
        if not row["until_handover"]:
            self.covered[date] = None
        elif self.covered.setdefault(date, set()) is not None:
            self.covered[date].update(row["shifts"])
        # Only a real rotation displaces anybody. A blank cycle is somebody
        # out every weekend regardless of whose turn it is.
        if row["cycle"]:
            self.cycles.setdefault(date, set()).add(row["cycle"])
        if row["cycle"] and row["group"]:
            self.owners.setdefault(date, set()).add((row["cycle"], row["group"]))

    def applies(self, slot: dict) -> bool:
        """Whether a closure claims this slot at all.

        No group closing the date means an ordinary working day; a Sunday
        past its handover belongs to whoever is relieved onto it.
        """
        date = slot["slot_date"]
        if not self.holders.get(date):
            return False
        limit = self.covered.get(date)
        return limit is None or slot["shift_name"] in limit

    def owner_label(self, date: str) -> str:
        return " ו".join(sorted(
            rotation_cycle.label(cycle, group)
            for cycle, group in self.owners.get(date, set())
        ))


def closure_availability(
    profile: dict, start: datetime.date, end: datetime.date, keys: set,
) -> List[dict]:
    """Hard rows keeping each closure day inside the group that owns it.

    A scheduler that balances every day on its own merits hands Saturday to
    whoever is under quota and breaks the cycle the unit planned around. So on
    a day some group is closing, everyone on a rotation who is *not* holding
    that day is marked unavailable. Someone with no pattern and no group is
    untouched, and an unanchored cycle produces nothing rather than a guess.
    """
    people = [
        person for person in (profile or {}).get("employees") or []
        if isinstance(person, dict) and bounded(person.get("name"))
    ]
    holdings = ClosureHoldings(profile, people, start, end)
    if not holdings.holders:
        return []
    result = []
    for slot in build_slots(profile, start.isoformat(), end.isoformat()):
        if not holdings.applies(slot):
            continue
        for person in people:
            if _displaced(profile, person, slot, holdings, keys):
                result.append(_blocked_row(
                    bounded(person.get("name")), slot,
                    "%s סוגר במועד זה" % holdings.owner_label(slot["slot_date"]),
                    source="closure",
                    rotation_group=bounded(person.get("rotation_group")),
                    derived_from="closure_cycle",
                ))
    return result


def _displaced(
    profile: dict, person: dict, slot: dict, holdings: ClosureHoldings,
    keys: set,
) -> bool:
    """Whether this person is kept out of a slot another group is closing.

    A person whose own cycle is not the one closing today is not displaced by
    it -- a תלתון soldier is not off because the round pair happens to be in.
    """
    name, date = bounded(person.get("name")), slot["slot_date"]
    if name in holdings.holders.get(date, set()):
        return False
    if not holdings.on_rotation.get(name):
        return False
    pattern = rotation_cycle.exit_pattern(profile, person)
    if _cycle_key(profile, person, pattern) not in holdings.cycles.get(date, set()):
        return False
    return not overridden(keys, name, date, slot["shift_name"])


def _on_rotation(profile: dict, person: dict) -> bool:
    """Whether the cycle has any claim on this person at all."""
    pattern = rotation_cycle.exit_pattern(profile, person)
    return pattern in _ROTATING_PATTERNS and bool(
        bounded(person.get("rotation_group"))
    )


def _cycle_key(profile: dict, person: dict, pattern: str) -> str:
    """The cycle a person turns on: their pattern, or their group's."""
    if pattern in ("round", "triplet"):
        return pattern
    if bounded(person.get("rotation_group")) == "ג":
        return "triplet"
    mode = bounded(((profile or {}).get("workplace") or {}).get("rotation_mode"))
    return mode if mode in ("round", "triplet") else "round"


def closures_for_model(profile: dict, start, end) -> List[dict]:
    """The period's closure cycle, per weekend, for the prompt."""
    if start is None or end is None:
        return []
    return rotation_cycle.schedule_for_model(profile, start, end)
