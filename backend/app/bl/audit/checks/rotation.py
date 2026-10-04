"""Assignments that put somebody in on another rotation's closure."""

from typing import Dict, List, Optional

from app.bl import rotation
from app.bl.audit.checks.base import AuditCheck, AuditInput
from app.bl.audit.codes import CROSS_ROTATION, SEVERITY_WARNING, warning
from app.bl.audit.roster import index_people
from app.bl.audit.values import parse_date, text

# The lettered groups each cycle turns through. Used to probe which dates a
# cycle closes without needing one of its people to be rostered that day.
_GROUPS_BY_CYCLE = {"round": ("א", "ב"), "triplet": ("א", "ב", "ג")}


def cycle_of(profile: dict, person: dict, pattern: str) -> str:
    """Which cycle a person turns on: their pattern, or their group's."""
    if pattern in ("round", "triplet"):
        return pattern
    if text(person.get("rotation_group")) == "ג":
        return "triplet"
    mode = text(((profile or {}).get("workplace") or {}).get("rotation_mode"))
    return mode if mode in ("round", "triplet") else "round"


class ClosingCalendar:
    """Who holds each date, which cycles close it, and which shifts it covers.

    Built once for the period rather than per row. Cycles are probed with a
    representative of every group, so a date counts even when nobody from the
    closing group is rostered -- and only closure *days* count, so an
    ordinary Tuesday belongs to nobody. `covered` maps a Sunday to the shifts
    before its handover; None means the whole day.
    """

    def __init__(self, profile: dict, people: Dict[str, dict], start, end):
        self.holders: Dict[str, set] = {}
        self.closing: Dict[str, set] = {}
        self.covered: Dict[str, Optional[set]] = {}
        for name, person in people.items():
            for row in rotation.closure_days(profile, person, start, end):
                self.holders.setdefault(row["date"], set()).add(name)
        # A group is what puts somebody in a rotation; without one they are
        # out every weekend rather than on a turn.
        cycles = {
            cycle_of(profile, person, rotation.exit_pattern(profile, person))
            for person in people.values()
            if text(person.get("rotation_group"))
        }
        for cycle in cycles:
            for group in _GROUPS_BY_CYCLE.get(cycle, ()):
                self._probe(profile, cycle, group, start, end)

    def _probe(self, profile, cycle: str, group: str, start, end) -> None:
        probe = {"exit_pattern": cycle, "rotation_group": group}
        for row in rotation.closure_days(profile, probe, start, end):
            date = row["date"]
            self.closing.setdefault(date, set()).add(cycle)
            if not row["until_handover"]:
                self.covered[date] = None
            elif self.covered.setdefault(date, set()) is not None:
                self.covered[date].update(row["shifts"])

    def covers(self, date: str, shift: str) -> bool:
        limit = self.covered.get(date)
        return limit is None or shift in limit


class CrossRotationCheck(AuditCheck):
    """Named apart from UNAVAILABLE because the manager needs the two apart.

    "יוסי has a doctor's appointment" is resolved by finding someone else;
    "יוסי is in on סבב א's Saturday" means the rotation itself has drifted.
    Reaching here means a schedule was imported, hand-edited, or built before
    the cycle was anchored. Silent when no cycle was anchored -- with no
    anchor there is no phase to be wrong about.
    """

    def run(self, data: AuditInput) -> List[dict]:
        people = index_people(data.profile.get("employees"))
        dates = sorted({text(row.get("date")) for row in data.rows if text(row.get("date"))})
        if not people or not dates:
            return []
        start, end = parse_date(dates[0]), parse_date(dates[-1])
        if start is None or end is None:
            return []
        calendar = ClosingCalendar(data.profile, people, start, end)
        if not calendar.closing:
            return []
        warnings = []
        for row in data.rows:
            found = self._check(data.profile, people, calendar, row)
            if found is not None:
                warnings.append(found)
        return warnings

    @staticmethod
    def _check(
        profile: dict, people: Dict[str, dict], calendar: ClosingCalendar,
        row: dict,
    ) -> Optional[dict]:
        name, date = text(row.get("employee")), text(row.get("date"))
        shift = text(row.get("shift"))
        person = people.get(name)
        if person is None or name in calendar.holders.get(date, set()):
            return None
        group = text(person.get("rotation_group"))
        if not group:
            # Nobody the cycle speaks for works an ordinary day here.
            return None
        pattern = rotation.exit_pattern(profile, person)
        if cycle_of(profile, person, pattern) not in calendar.closing.get(date, set()):
            # A different cycle is closing today; this one has no claim.
            return None
        if not calendar.covers(date, shift):
            # Past the handover on the Sunday a closure ends.
            return None
        holding = sorted(calendar.holders.get(date, set()))
        return warning(
            CROSS_ROTATION,
            SEVERITY_WARNING,
            "%s (קבוצה %s) משובץ ל%s בתאריך %s, "
            "אך הסגירה במועד זה אינה של קבוצתו%s."
            % (name, group, shift, date, _holders_note(holding)),
            employee=name, date=date, shift=shift,
            details={
                "rotation_group": group,
                "exit_pattern": pattern,
                "closing_employees": holding,
            },
        )


def _holders_note(holding: List[str]) -> str:
    if not holding:
        return ""
    return " (סוגרים: %s%s)" % (
        ", ".join(holding[:3]), " ואחרים" if len(holding) > 3 else "",
    )
