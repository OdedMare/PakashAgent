"""`audit()`: every warning the countable facts support, most severe first."""

from typing import List, Optional, Sequence

from app.bl.audit.checks import DEFAULT_CHECKS, AuditCheck, AuditInput
from app.bl.audit.codes import severity_rank


class Auditor:
    def __init__(self, checks: Sequence[AuditCheck] = DEFAULT_CHECKS):
        self._checks = checks

    def run(self, data: AuditInput) -> List[dict]:
        warnings: List[dict] = []
        for check in self._checks:
            warnings.extend(check.run(data))
        # Sorted for a stable render: a list that reorders itself between two
        # identical audits looks like the schedule changed when it did not.
        warnings.sort(key=lambda item: (
            severity_rank(item["severity"]),
            item.get("date") or "",
            item["code"],
            item.get("employee") or "",
        ))
        return warnings


_DEFAULT = Auditor()


def audit(
    assignments: List[dict],
    shifts: List[dict],
    employees: List[dict],
    availability: Optional[List[dict]] = None,
    profile: Optional[dict] = None,
    slots: Optional[List[dict]] = None,
) -> List[dict]:
    """Every warning the countable facts support, most severe first.

    `assignments` are person -> shift -> date rows. `shifts` and `employees`
    come from the workplace profile, which is why shift names are read from
    the data rather than known here (D9).

    `slots` is the schedule's own grid. A slot with *nobody* on it leaves no
    trace in `assignments`, so without the grid an entirely unstaffed shift
    is invisible -- the case the unfilled warning exists for.

    Returns a list; it does not raise on a broken rule, because a broken rule
    is a thing to report rather than an error in the caller.
    """
    return _DEFAULT.run(AuditInput(
        assignments, shifts, employees, availability, profile, slots,
    ))
