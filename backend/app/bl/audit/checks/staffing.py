"""Slots short of headcount, roles, or a commander -- and slots over headcount."""

from typing import Dict, List

from app.bl.audit.checks.base import AuditCheck, AuditInput
from app.bl.audit.codes import (
    MISSING_COMMANDER, MISSING_ROLE, OVERSTAFFED, SEVERITY_NOTICE,
    SEVERITY_WARNING, UNFILLED, warning,
)
from app.bl.audit.roster import index_people
from app.bl.audit.staffing_rules import (
    checked_slots, counted_rows, required_headcount, required_roles,
    requires_shift_manager, seat_counts,
)
from app.bl.audit.values import parse_date, text


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
    def _filled_roles(data: AuditInput, people: Dict[str, dict]) -> Dict[tuple, set]:
        filled: Dict[tuple, set] = {}
        for row in counted_rows(data.rows, data.employees, data.profile):
            person = people.get(row["employee"], {})
            held = person.get("roles")
            if not isinstance(held, list):
                held = [person.get("role")]
            filled.setdefault((row["date"], row["shift"]), set()).update(
                text(role) for role in held if text(role)
            )
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
        data: AuditInput, filled: Dict[tuple, set], date: str, shift_name: str,
    ) -> List[dict]:
        present = filled.get((date, shift_name), set())
        return [
            warning(
                MISSING_ROLE, SEVERITY_WARNING,
                "במשמרת %s בתאריך %s חסר התפקיד הנדרש %s."
                % (shift_name, date, role),
                date=date, shift=shift_name,
                details={"required_role": role},
            )
            for role in required_roles(
                data.shifts, shift_name, parse_date(date), data.slots
            )
            if role not in present
        ]
