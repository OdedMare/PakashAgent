"""Whether an assignment falls outside a recorded availability."""

from app.bl.audit.values import MINUTES_PER_DAY, minutes, text


def constraint_conflicts(assignment: dict, constraint: dict) -> bool:
    """Whether one assignment falls outside one recorded availability.

    The same arithmetic feeds candidate filtering and the advisory audit.
    `available=True` plus times means the employee may work only inside that
    window; `available=False` plus times means that window itself is blocked.
    With no times, the whole-day/whole-shift behaviour applies.
    """
    if not isinstance(assignment, dict) or not isinstance(constraint, dict):
        return False
    if not _same_occurrence(assignment, constraint):
        return False
    start_bound = minutes(constraint.get("start_time"))
    end_bound = minutes(constraint.get("end_time"))
    if start_bound is None and end_bound is None:
        return not bool(constraint.get("available"))

    shift_start = minutes(assignment.get("start") or assignment.get("start_time"))
    shift_end = minutes(assignment.get("end") or assignment.get("end_time"))
    # A timed constraint cannot be evaluated against a shift whose hours the
    # workplace never defined; unknown hours are not a conflict.
    if shift_start is None or shift_end is None:
        return False
    if shift_end <= shift_start:
        shift_end += MINUTES_PER_DAY
    if constraint.get("available"):
        return _outside_window(shift_start, shift_end, start_bound, end_bound)
    return _overlaps_block(shift_start, shift_end, start_bound, end_bound)


def _same_occurrence(assignment: dict, constraint: dict) -> bool:
    if text(assignment.get("employee")) != text(constraint.get("employee")):
        return False
    if text(assignment.get("date")) != text(
        constraint.get("date") or constraint.get("constraint_date")
    ):
        return False
    constrained = text(constraint.get("shift") or constraint.get("shift_name"))
    return not constrained or constrained == text(assignment.get("shift"))


def _outside_window(shift_start, shift_end, start_bound, end_bound) -> bool:
    window_end = end_bound
    if start_bound is not None and window_end is not None and window_end <= start_bound:
        window_end += MINUTES_PER_DAY
    return (
        (start_bound is not None and shift_start < start_bound)
        or (window_end is not None and shift_end > window_end)
    )


def _overlaps_block(shift_start, shift_end, start_bound, end_bound) -> bool:
    blocked_start = start_bound if start_bound is not None else 0
    blocked_end = end_bound if end_bound is not None else MINUTES_PER_DAY
    if start_bound is not None and end_bound is not None and blocked_end <= blocked_start:
        blocked_end += MINUTES_PER_DAY
    return shift_start < blocked_end and blocked_start < shift_end


def constraint_window(item: dict) -> str:
    start, end = text(item.get("start_time")), text(item.get("end_time"))
    if start and end:
        return "%s–%s" % (start, end)
    if start:
        return "החל מ-%s" % start
    if end:
        return "עד %s" % end
    return ""
