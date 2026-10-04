"""What every check reads, and the one method every check implements."""

from typing import Dict, List, Optional

from app.bl.audit.roster import index_shifts, policy, rows_of


class AuditInput:
    """A schedule prepared once for every check: rows, vocabulary, policy."""

    def __init__(
        self,
        assignments: List[dict],
        shifts: List[dict],
        employees: List[dict],
        availability: Optional[List[dict]] = None,
        profile: Optional[dict] = None,
        slots: Optional[List[dict]] = None,
    ):
        self.shifts = shifts or []
        self.employees = employees or []
        self.availability = availability or []
        self.profile = profile or {}
        self.slots = slots
        self.shift_index: Dict[str, dict] = index_shifts(shifts)
        self.policy = policy(profile)
        self.rows = rows_of(assignments, self.shift_index)


class AuditCheck:
    """One countable fact about a schedule, reported as warnings.

    A check returns warnings and nothing else. It never raises on a broken
    rule and never returns something a caller is expected to branch on before
    saving -- that would make the audit the authority D3 says it is not.
    """

    def run(self, data: AuditInput) -> List[dict]:
        raise NotImplementedError
