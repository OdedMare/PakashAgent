"""Warning codes, severities, and the one shape every warning takes."""

from typing import Optional

# Warning codes. Strings rather than an enum so they survive a JSON round
# trip to the UI and back unchanged, and so a new check does not require a
# frontend that knows about it in order to render.
OVER_HOURS = "over_hours"
CONSECUTIVE = "consecutive"
SHORT_REST = "short_rest"
DOUBLE_BOOKED = "double_booked"
UNAVAILABLE = "unavailable"
UNFILLED = "unfilled"
OVERSTAFFED = "overstaffed"
MISSING_ROLE = "missing_role"
MISSING_COMMANDER = "missing_commander"
CROSS_ROTATION = "cross_rotation"

# Severity is advice about presentation, not authority. `warning` is a thing
# the manager should look at; `notice` is a thing worth mentioning. Neither
# blocks, and the UI renders both as non-blocking banners.
SEVERITY_WARNING = "warning"
SEVERITY_NOTICE = "notice"


def warning(
    code: str,
    severity: str,
    message: str,
    employee: str = "",
    date: str = "",
    shift: str = "",
    details: Optional[dict] = None,
) -> dict:
    """One advisory warning. Hebrew message, machine-readable code."""
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "employee": employee,
        "date": date,
        "shift": shift,
        "details": details or {},
    }


def severity_rank(severity: str) -> int:
    return 0 if severity == SEVERITY_WARNING else 1
