"""Assignments outside group presence, using the same gate as generation."""

from typing import List

from app.bl.rotation.presence import closure_status, presence_status
from app.bl.rotation.vocabulary import exit_pattern, label
from app.bl.audit.checks.base import AuditCheck, AuditInput
from app.bl.audit.codes import CROSS_ROTATION, SEVERITY_WARNING, warning
from app.bl.audit.roster import index_people
from app.bl.audit.values import text


class CrossRotationCheck(AuditCheck):
    def run(self, data: AuditInput) -> List[dict]:
        people = index_people(data.profile.get("employees"))
        profile = dict(data.profile, shifts=data.shifts)
        shifts = data.shift_index
        warnings = []
        for row in data.rows:
            name, date, shift = text(row.get("employee")), text(row.get("date")), text(row.get("shift"))
            person = people.get(name)
            if person is None or not date:
                continue
            slot = dict(shifts.get(shift) or {}, slot_date=date, shift_name=shift)
            status = presence_status(profile, person, slot)
            if status is None:
                status = closure_status(profile, person, slot)
            if status is False:
                warnings.append(warning(
                    CROSS_ROTATION, SEVERITY_WARNING,
                    "%s (%s) משובץ ל%s בתאריך %s מחוץ לזמני הנוכחות של קבוצתו."
                    % (name, label(exit_pattern(data.profile, person), person.get("rotation_group")), shift, date),
                    employee=name, date=date, shift=shift,
                    details=dict(rotation_group=text(person.get("rotation_group")),
                                 exit_pattern=exit_pattern(data.profile, person)),
                ))
        return warnings
