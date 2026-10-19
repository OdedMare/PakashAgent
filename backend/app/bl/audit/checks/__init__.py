"""The individual audit checks. Each is one class with one `run` method.

Adding a check is adding a class to `DEFAULT_CHECKS`; nothing else changes.
"""

from app.bl.audit.checks.base import AuditCheck, AuditInput
from app.bl.audit.checks.people import (
    ConsecutiveDaysCheck,
    DoubleBookedCheck,
    OverHoursCheck,
    ShortRestCheck,
    UnavailableCheck,
)
from app.bl.audit.checks.rotation import CrossRotationCheck
from app.bl.audit.checks.staffing import StaffingCheck

DEFAULT_CHECKS = (
    DoubleBookedCheck(),
    UnavailableCheck(),
    OverHoursCheck(),
    ConsecutiveDaysCheck(),
    ShortRestCheck(),
    StaffingCheck(),
    CrossRotationCheck(),
)

__all__ = ["AuditCheck", "AuditInput", "DEFAULT_CHECKS"]
