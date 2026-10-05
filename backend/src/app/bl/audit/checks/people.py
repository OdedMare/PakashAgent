"""Checks about one person's week: bookings, availability, hours, rest."""

import datetime
from typing import Dict, List

from app.bl.audit.checks.base import AuditCheck, AuditInput
from app.bl.audit.codes import (
    CONSECUTIVE, DOUBLE_BOOKED, OVER_HOURS, SEVERITY_NOTICE, SEVERITY_WARNING,
    SHORT_REST, UNAVAILABLE, warning,
)
from app.bl.audit.constraints import constraint_conflicts, constraint_window
from app.bl.audit.roster import ends_at, iso_week, starts_at
from app.bl.audit.values import number, text


class DoubleBookedCheck(AuditCheck):
    """One person in two places in one slot.

    Keyed on person+date+shift. Two *different* shifts on one day may be
    legitimate (a split day); where they overlap in time, `ShortRestCheck`
    reports it.
    """

    def run(self, data: AuditInput) -> List[dict]:
        seen: Dict[tuple, int] = {}
        for row in data.rows:
            key = (row["employee"], row["date"], row["shift"])
            seen[key] = seen.get(key, 0) + 1
        return [
            warning(
                DOUBLE_BOOKED, SEVERITY_WARNING,
                "%s משובץ %d פעמים למשמרת %s בתאריך %s."
                % (employee, count, shift, date),
                employee=employee, date=date, shift=shift,
            )
            for (employee, date, shift), count in seen.items() if count > 1
        ]


class UnavailableCheck(AuditCheck):
    """Assignments that contradict hard or soft availability windows."""

    def run(self, data: AuditInput) -> List[dict]:
        warnings = []
        for row in data.rows:
            item = next(
                (item for item in data.availability
                 if constraint_conflicts(row, item)),
                None,
            )
            if item is not None:
                warnings.append(self._warning(row, item))
        return warnings

    @staticmethod
    def _warning(row: dict, item: dict) -> dict:
        reason = text(item.get("reason"))
        hard = item.get("is_hard", True) is not False
        window = constraint_window(item)
        return warning(
            UNAVAILABLE,
            SEVERITY_WARNING if hard else SEVERITY_NOTICE,
            "%s משובץ ל%s בתאריך %s בניגוד ל%s%s%s."
            % (row["employee"], row["shift"], row["date"],
               "אילוץ" if hard else "העדפה",
               " (%s)" % window if window else "",
               " (%s)" % reason if reason else ""),
            employee=row["employee"], date=row["date"], shift=row["shift"],
            details={
                "is_hard": hard,
                "start_time": text(item.get("start_time")),
                "end_time": text(item.get("end_time")),
            },
        )


class OverHoursCheck(AuditCheck):
    """Weekly hours past the ceiling, per person.

    Weeks are ISO weeks off the assignment date rather than the planning
    period: a person's rest does not reset because a new schedule started
    midweek.
    """

    def run(self, data: AuditInput) -> List[dict]:
        limits = self._limits(data.employees)
        totals: Dict[tuple, float] = {}
        for row in data.rows:
            if row["day"] is not None:
                key = (row["employee"],) + iso_week(row["day"])
                totals[key] = totals.get(key, 0.0) + row["hours"]
        warnings = []
        for (employee, year, week), hours in totals.items():
            limit = limits.get(employee, data.policy["max_weekly_hours"])
            if hours > limit:
                warnings.append(warning(
                    OVER_HOURS, SEVERITY_WARNING,
                    "ל%s יש %.1f שעות בשבוע %d/%d, מעל התקרה של %.1f."
                    % (employee, hours, week, year, limit),
                    employee=employee,
                    details={"hours": round(hours, 2), "limit": limit,
                             "week": week, "year": year},
                ))
        return warnings

    @staticmethod
    def _limits(employees: List[dict]) -> Dict[str, float]:
        limits = {}
        for employee in employees:
            if not isinstance(employee, dict) or not text(employee.get("name")):
                continue
            limit = number(employee.get("max_weekly_hours"), 0.0)
            if limit > 0:
                limits[text(employee.get("name"))] = limit
        return limits


class ConsecutiveDaysCheck(AuditCheck):
    """Runs of consecutive worked days past the ceiling.

    Counts distinct days: two shifts on one day are one day worked here, and
    the thing that makes them a problem is rest, reported separately.
    """

    def run(self, data: AuditInput) -> List[dict]:
        days: Dict[str, set] = {}
        for row in data.rows:
            if row["day"] is not None:
                days.setdefault(row["employee"], set()).add(row["day"])
        limit = data.policy["max_consecutive_days"]
        return [
            warning(
                CONSECUTIVE, SEVERITY_WARNING,
                "%s עובד %d ימים ברצף מ-%s, מעל המקסימום של %d."
                % (employee, length, start.isoformat(), limit),
                employee=employee, date=start.isoformat(),
                details={"days": length, "limit": limit},
            )
            for employee, worked in days.items()
            for start, length in runs(sorted(worked))
            if length > limit
        ]


def runs(days: List[datetime.date]) -> List[tuple]:
    """(first day, length) for each maximal run of consecutive dates."""
    found = []
    start = previous = None
    length = 0
    for day in days:
        if previous is not None and (day - previous).days == 1:
            length += 1
        else:
            if start is not None:
                found.append((start, length))
            start, length = day, 1
        previous = day
    if start is not None:
        found.append((start, length))
    return found


class ShortRestCheck(AuditCheck):
    """Too little time between the end of one shift and the next one's start.

    Also what catches two shifts that genuinely overlap: they come out as a
    negative gap, the same class of problem -- the person cannot be in both.
    """

    def run(self, data: AuditInput) -> List[dict]:
        minimum = data.policy["min_rest_hours"]
        by_employee: Dict[str, List[dict]] = {}
        for row in data.rows:
            if row["day"] is not None and row["start"] is not None \
                    and row["end"] is not None:
                by_employee.setdefault(row["employee"], []).append(row)
        warnings = []
        for employee, worked in by_employee.items():
            ordered = sorted(worked, key=starts_at)
            for earlier, later in zip(ordered, ordered[1:]):
                gap = (starts_at(later) - ends_at(earlier)).total_seconds() / 3600.0
                if gap < minimum:
                    warnings.append(_short_rest(employee, earlier, later, gap, minimum))
        return warnings


def _short_rest(employee, earlier, later, gap, minimum) -> dict:
    return warning(
        SHORT_REST, SEVERITY_WARNING,
        "ל%s יש %.1f שעות מנוחה בין %s ב-%s לבין %s ב-%s, פחות מ-%.1f."
        % (employee, gap, earlier["shift"], earlier["date"],
           later["shift"], later["date"], minimum),
        employee=employee, date=later["date"], shift=later["shift"],
        details={"rest_hours": round(gap, 2), "minimum": minimum},
    )
