"""Slots short of headcount, roles, or a commander -- and slots over headcount."""

from typing import Dict, List

from app.bl.audit.checks.base import AuditCheck, AuditInput
from app.bl.audit.codes import (
    FALLBACK_ROLE, MISSING_COMMANDER, MISSING_ROLE, OVERSTAFFED, SEVERITY_NOTICE,
    SEVERITY_WARNING, UNFILLED, warning,
)
from app.bl.audit.roster import index_people
from app.bl.audit.staffing_rules import (
    checked_slots, counted_rows, required_headcount, required_roles,
    requires_shift_manager, seat_counts,
)
from app.bl.audit.unit_policy import cover, fallbacks, held_roles, role_needs
from app.bl.shared import parse_date


class StaffingCheck(AuditCheck):
    """Understaffing is a warning -- somebody does not show up. Overstaffing
    is a notice: it costs money but nothing breaks, and the manager may have
    done it deliberately for training or cover.
    """

    def run(self, data: AuditInput) -> List[dict]:
        people = index_people(data.employees)
        filled = seat_counts(data.rows, data.employees, data.profile)
        roles = self._filled_roles(data, people)
        commanded = {
            (row["date"], row["shift"]) for row in data.rows
            if people.get(row["employee"], {}).get("is_shift_manager")
        }
        warnings = []
        for date, shift_name in sorted(checked_slots(data.rows, data.slots)):
            warnings.extend(self._headcount(data, filled, date, shift_name))
            warnings.extend(self._roles(data, roles, date, shift_name))
            if requires_shift_manager(data.shifts, shift_name, date, data.slots) \
                    and (date, shift_name) not in commanded:
                warnings.append(warning(
                    MISSING_COMMANDER, SEVERITY_WARNING,
                    "במשמרת %s בתאריך %s חסר/ה מפקד/ת משמרת מוסמך/ת."
                    % (shift_name, date),
                    date=date, shift=shift_name,
                    details={"requires_shift_manager": True},
                ))
        return warnings

    @staticmethod
    def _filled_roles(data: AuditInput, people: Dict[str, dict]) -> Dict[tuple, list]:
        """Per slot, the roles each counted person on it holds."""
        filled: Dict[tuple, list] = {}
        for row in counted_rows(data.rows, data.employees, data.profile):
            filled.setdefault((row["date"], row["shift"]), []).append(
                held_roles(people.get(row["employee"], {})))
        return filled

    @staticmethod
    def _headcount(
        data: AuditInput, filled: Dict[tuple, int], date: str, shift_name: str,
    ) -> List[dict]:
        needed = required_headcount(
            data.shifts, shift_name, parse_date(date), data.slots
        )
        if needed is None:
            return []
        count = filled.get((date, shift_name), 0)
        details = {"assigned": count, "required": needed}
        if count < needed:
            return [warning(
                UNFILLED, SEVERITY_WARNING,
                "במשמרת %s בתאריך %s משובצים %d מתוך %d."
                % (shift_name, date, count, needed),
                date=date, shift=shift_name, details=details,
            )]
        if count > needed:
            return [warning(
                OVERSTAFFED, SEVERITY_NOTICE,
                "במשמרת %s בתאריך %s משובצים %d במקום %d."
                % (shift_name, date, count, needed),
                date=date, shift=shift_name, details=details,
            )]
        return []

    @staticmethod
    def _roles(
        data: AuditInput, filled: Dict[tuple, list], date: str, shift_name: str,
    ) -> List[dict]:
        """A role listed N times needs N holders, one seat each; a holder of
        a fallback role fills a seat with a notice."""
        needs = role_needs(required_roles(
            data.shifts, shift_name, parse_date(date), data.slots))
        if not needs:
            return []
        missing, substituted = cover(
            filled.get((date, shift_name), []), needs, fallbacks(data.profile))
        warnings = [
            warning(
                MISSING_ROLE, SEVERITY_WARNING,
                "במשמרת %s בתאריך %s חסר התפקיד הנדרש %s%s."
                % (shift_name, date, role, "" if count == 1 else " (%d)" % count),
                date=date, shift=shift_name,
                details=dict({"required_role": role}, **({"missing": count} if count > 1 else {})),
            )
            for role, count in sorted(missing.items())
        ]
        if substituted:
            warnings.append(warning(
                FALLBACK_ROLE, SEVERITY_NOTICE,
                "במשמרת %s בתאריך %s %d תפקידים מאוישים בעדיפות שנייה (תפקיד חלופי)."
                % (shift_name, date, substituted),
                date=date, shift=shift_name, details={"substituted": substituted},
            ))
        return warnings
