"""The unit's staffing standard (`unit_policy.py`): weak crews, a soldier
below a strong shift's level, weekly shift limits, a reservist's days a
week and stale qualifications.
Warnings only, like every check."""

from collections import Counter
from typing import Dict, List

from app.bl.audit.checks.base import AuditCheck, AuditInput
from app.bl.audit.codes import (
    BELOW_LEVEL, QUALIFICATION_EXPIRED, RESERVE_DAYS, SEVERITY_NOTICE, SEVERITY_WARNING, WEAK_CREW,
    WEEKLY_SHIFTS, warning,
)
from app.bl.audit.roster import index_people
from app.bl.audit.staffing_rules import required_roles
from app.bl.audit.unit_policy import (
    below_level, is_weak, max_weak, qualification_expired, reserve_days, role_needs, unit_week,
    weekly_limits,
)
from app.bl.shared import parse_date

LEVEL_NAMES = {"weak": "חלשה", "medium": "בינונית", "high": "גבוהה", "excellent": "מצטיינת"}


class UnitStandardCheck(AuditCheck):
    def run(self, data: AuditInput) -> List[dict]:
        people = index_people(data.employees)
        return self._weak(data, people) + self._level(data, people) \
            + self._weekly(data, people) \
            + self._reserve(data, people) + self._stale(data, people)

    @staticmethod
    def _weak(data: AuditInput, people: Dict[str, dict]) -> List[dict]:
        cap = max_weak(data.profile)
        if cap is None:
            return []
        weak = Counter((row["date"], row["shift"]) for row in data.rows
                       if is_weak(people.get(row["employee"])))
        return [
            warning(WEAK_CREW, SEVERITY_WARNING,
                    "במשמרת %s בתאריך %s משובצים %d בעלי רמה מקצועית חלשה (המותר: %d)."
                    % (shift, date, count, cap),
                    date=date, shift=shift, details={"weak": count, "allowed": cap})
            for (date, shift), count in sorted(weak.items()) if count > cap
        ]

    @staticmethod
    def _level(data: AuditInput, people: Dict[str, dict]) -> List[dict]:
        """A rated soldier on a shift that asks for a higher רמה מקצועית
        (`min_competence`). Named on the soldier, so their own card says
        it, rather than on the cell like a weak crew."""
        warnings = []
        for row in data.rows:
            found = below_level(people.get(row["employee"]), data.shift_index.get(row["shift"]))
            if found is None:
                continue
            have, need = found
            warnings.append(warning(
                BELOW_LEVEL, SEVERITY_WARNING,
                "%s (רמה מקצועית %s) משובץ/ת ל%s בתאריך %s, משמרת חזקה שדורשת רמה %s לפחות."
                % (row["employee"], LEVEL_NAMES[have], row["shift"], row["date"], LEVEL_NAMES[need]),
                employee=row["employee"], date=row["date"], shift=row["shift"],
                details={"competence": have, "required": need}))
        return warnings

    @staticmethod
    def _weekly(data: AuditInput, people: Dict[str, dict]) -> List[dict]:
        counts = Counter()
        for row in data.rows:
            day = parse_date(row["date"])
            if day:
                counts[(row["employee"], unit_week(day))] += 1
        warnings = []
        for (name, week), count in sorted(counts.items()):
            low, high = weekly_limits(data.profile, people.get(name))
            if high is not None and count > high:
                warnings.append(warning(
                    WEEKLY_SHIFTS, SEVERITY_WARNING,
                    "%s שובץ/ה ל-%d משמרות בשבוע שמתחיל ב-%s, מעל המקסימום (%d)."
                    % (name, count, week.isoformat(), high),
                    employee=name, details={"week": week.isoformat(), "shifts": count, "max": high}))
            elif count < low:
                warnings.append(warning(
                    WEEKLY_SHIFTS, SEVERITY_NOTICE,
                    "%s שובץ/ה ל-%d משמרות בשבוע שמתחיל ב-%s, מתחת למינימום (%d)."
                    % (name, count, week.isoformat(), low),
                    employee=name, details={"week": week.isoformat(), "shifts": count, "min": low}))
        return warnings

    @staticmethod
    def _reserve(data: AuditInput, people: Dict[str, dict]) -> List[dict]:
        """A reservist on more distinct days in a Sunday–Saturday week than
        `reserve_days_per_week`. The solver never builds one; a pin, a hand
        placement or a cover picked in the chat can."""
        worked: Dict[tuple, set] = {}
        for row in data.rows:
            day = parse_date(row["date"])
            if day and reserve_days(people.get(row["employee"])) is not None:
                worked.setdefault((row["employee"], unit_week(day)), set()).add(day)
        warnings = []
        for (name, week), days in sorted(worked.items()):
            cap = reserve_days(people.get(name))
            if len(days) > cap:
                warnings.append(warning(
                    RESERVE_DAYS, SEVERITY_WARNING,
                    "%s (מילואים) משובץ/ת %d ימים בשבוע שמתחיל ב-%s, מעל %d הימים שהוא/היא מגיע/ה."
                    % (name, len(days), week.isoformat(), cap),
                    # Dated on the first day past the cap: the day to move.
                    employee=name, date=sorted(days)[cap].isoformat(),
                    details={"week": week.isoformat(), "days": len(days), "max": cap}))
        return warnings

    @staticmethod
    def _stale(data: AuditInput, people: Dict[str, dict]) -> List[dict]:
        """A person placed where their only qualification for a required
        role there has lapsed. Reported once per person and role."""
        seen, warnings = set(), []
        for row in sorted(data.rows, key=lambda item: item["date"]):
            day, person = parse_date(row["date"]), people.get(row["employee"])
            if not day or not person:
                continue
            needed = role_needs(required_roles(data.shifts, row["shift"], day, data.slots))
            for role in sorted(needed):
                key = (row["employee"], role)
                if key in seen or not qualification_expired(data.profile, person, role, day):
                    continue
                seen.add(key)
                warnings.append(warning(
                    QUALIFICATION_EXPIRED, SEVERITY_NOTICE,
                    "הכשירות של %s לתפקיד %s פגה (לא פעיל/ה בתקופת התוקף), והוא/היא משובץ/ת ב-%s."
                    % (row["employee"], role, row["date"]),
                    employee=row["employee"], date=row["date"], shift=row["shift"],
                    details={"role": role}))
        return warnings


__all__ = ["UnitStandardCheck"]
