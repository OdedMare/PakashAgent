"""Advisory checks over a schedule. Pure Python, no LLM, never blocks.

This is the counterweight to [D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-):
the agent makes every scheduling decision, and code recomputes only the
things that are *countable* — hours, consecutive shifts, double-booking,
availability conflicts, unfilled slots. Arithmetic over a roster is the one
thing an LLM gets subtly wrong in a way that looks exactly like getting it
right, so it is the one thing that is not left to the model.

Everything here returns warnings. Nothing here rejects a schedule, rewrites
an assignment, or vetoes the agent. If this module ever grows a `raise` on a
rule violation or a return value the caller is expected to branch on before
saving, D3 has been reversed — re-read it before doing that.

No model call, ever. The entire value of this file is being arithmetic that
cannot be hallucinated, which is also what makes it exhaustively testable
against a table of fixtures.
"""

import datetime
from typing import Any, Dict, List, Optional

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

# Severity is advice about presentation, not authority. `warning` is a thing
# the manager should look at; `notice` is a thing worth mentioning. Neither
# blocks, and the UI renders both as non-blocking banners.
SEVERITY_WARNING = "warning"
SEVERITY_NOTICE = "notice"

# Defaults used only when the workplace profile does not say otherwise. Every
# one of these is overridden by what the interview collected -- these exist so
# a schedule can be audited before the profile is complete, not to encode a
# policy about what a working week looks like.
_DEFAULT_MAX_WEEKLY_HOURS = 45.0
_DEFAULT_MAX_CONSECUTIVE_DAYS = 6
_DEFAULT_MIN_REST_HOURS = 8.0
# A shift whose end time is at or before its start crosses midnight. There is
# no date arithmetic to do here beyond that: shifts are bounded by a day.
_MINUTES_PER_HOUR = 60.0


def audit(
    assignments: List[dict],
    shifts: List[dict],
    employees: List[dict],
    availability: Optional[List[dict]] = None,
    profile: Optional[dict] = None,
    slots: Optional[List[dict]] = None,
) -> List[dict]:
    """Every warning the countable facts support, most severe first.

    `assignments` are person -> shift -> date rows as `dal/repository`
    stores them. `shifts` and `employees` come from the workplace profile,
    which is why shift names are read from the data rather than known here
    ([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).

    `slots` is the schedule's own grid — every shift on every date the period
    contains. It matters because a slot with *nobody* on it leaves no trace in
    `assignments`: without the grid, an entirely unstaffed shift is invisible
    to a check that walks the assignments, which is precisely the case the
    unfilled-slot warning exists for. Callers that have a stored schedule pass
    it; the assignments are the fallback when they do not.

    Returns a list; it does not raise on a broken rule, because a broken rule
    is a thing to report rather than an error in the caller.
    """
    shift_index = _index_shifts(shifts)
    policy = _policy(profile)
    rows = [_row(item, shift_index) for item in assignments or []]
    rows = [row for row in rows if row is not None]

    warnings: List[dict] = []
    warnings.extend(_double_booked(rows))
    warnings.extend(_unavailable(rows, availability or []))
    warnings.extend(_over_hours(rows, employees or [], policy))
    warnings.extend(_consecutive_days(rows, policy))
    warnings.extend(_short_rest(rows, shift_index, policy))
    warnings.extend(_staffing(rows, shifts or [], slots))
    # Sorted for a stable render: the manager reads this list top-down, and a
    # set of warnings that reorders itself between two identical audits looks
    # like the schedule changed when it did not.
    warnings.sort(key=lambda item: (
        0 if item["severity"] == SEVERITY_WARNING else 1,
        item.get("date") or "",
        item["code"],
        item.get("employee") or "",
    ))
    return warnings


def _policy(profile: Optional[dict]) -> dict:
    """Thresholds, taken from the profile where it states them.

    The interview collects rest and weekend policy as the manager's own
    sentences ([D2](../../../docs/DECISIONS.md#d2--rules-stay-natural-language)),
    which is not a number this can read. So the numeric thresholds come from
    an explicit `audit_policy` block when one exists and fall back to the
    defaults otherwise -- deliberately NOT parsed out of the Hebrew prose,
    which would be exactly the guessing this module exists to avoid.
    """
    policy = (profile or {}).get("audit_policy")
    policy = policy if isinstance(policy, dict) else {}
    return {
        "max_weekly_hours": _number(
            policy.get("max_weekly_hours"), _DEFAULT_MAX_WEEKLY_HOURS
        ),
        "max_consecutive_days": int(_number(
            policy.get("max_consecutive_days"), _DEFAULT_MAX_CONSECUTIVE_DAYS
        )),
        "min_rest_hours": _number(
            policy.get("min_rest_hours"), _DEFAULT_MIN_REST_HOURS
        ),
    }


def _index_shifts(shifts: Optional[List[dict]]) -> Dict[str, dict]:
    """Shift definitions by name.

    Names are data from the workplace's own vocabulary, never literals
    ([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
    """
    index: Dict[str, dict] = {}
    for shift in shifts or []:
        if not isinstance(shift, dict):
            continue
        name = _text(shift.get("name"))
        if name:
            index[name] = shift
    return index


def _row(item: Any, shift_index: Dict[str, dict]) -> Optional[dict]:
    """One assignment, normalized, with its shift's hours resolved.

    An assignment naming a shift the vocabulary does not have is kept rather
    than dropped: it still double-books and still fills a slot. It simply
    contributes no hours, because nothing here knows how long it is -- and
    inventing a length would put a fabricated number in the hours total.
    """
    if not isinstance(item, dict):
        return None
    employee = _text(item.get("employee"))
    shift_name = _text(item.get("shift"))
    date = _text(item.get("date"))
    if not employee or not date:
        return None
    shift = shift_index.get(shift_name) or {}
    return {
        "employee": employee,
        "shift": shift_name,
        "date": date,
        "day": _parse_date(date),
        "start": _parse_time(shift.get("start_time")),
        "end": _parse_time(shift.get("end_time")),
        "hours": _shift_hours(shift),
        "is_on_call": bool(shift.get("is_on_call")),
    }


def _shift_hours(shift: dict) -> float:
    """Clock length times the shift's hour weight.

    On-call is the reason the weight exists: `כונן לילה` in one of the real
    files is a night a person is *available* rather than working, and the
    interview asks how it counts toward hours precisely so this does not
    have to assume ([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
    A weight of 0.5 makes an eight-hour on-call count as four.
    """
    start = _parse_time(shift.get("start_time"))
    end = _parse_time(shift.get("end_time"))
    if start is None or end is None:
        return 0.0
    minutes = (end - start).total_seconds() / 60.0 if end > start else (
        (end - start).total_seconds() / 60.0 + 24 * _MINUTES_PER_HOUR
    )
    weight = _number(shift.get("hour_weight"), 1.0)
    return round((minutes / _MINUTES_PER_HOUR) * weight, 2)


def _double_booked(rows: List[dict]) -> List[dict]:
    """One person in two places in one slot.

    Keyed on person+date+shift, so the same person twice on the same shift is
    the duplicate this catches. Two *different* shifts on one day may be
    legitimate (a split day), and where they actually overlap in time
    `_short_rest` is what reports it.
    """
    seen: Dict[tuple, int] = {}
    for row in rows:
        key = (row["employee"], row["date"], row["shift"])
        seen[key] = seen.get(key, 0) + 1
    warnings = []
    for (employee, date, shift), count in seen.items():
        if count > 1:
            warnings.append(_warning(
                DOUBLE_BOOKED, SEVERITY_WARNING,
                "%s משובץ %d פעמים למשמרת %s בתאריך %s."
                % (employee, count, shift, date),
                employee=employee, date=date, shift=shift,
            ))
    return warnings


def _unavailable(rows: List[dict], availability: List[dict]) -> List[dict]:
    """An assignment that contradicts a recorded unavailability.

    A row whose `shift` is empty blocks the whole day -- that is the daily
    constraint the interview asks about explicitly ("does a daily constraint
    rule out every shift that day?"), stored as a row with no shift name.
    """
    blocked = set()
    reasons: Dict[tuple, str] = {}
    for item in availability or []:
        if not isinstance(item, dict) or item.get("available"):
            continue
        employee = _text(item.get("employee"))
        date = _text(item.get("date"))
        if not employee or not date:
            continue
        shift = _text(item.get("shift"))
        blocked.add((employee, date, shift))
        reasons[(employee, date, shift)] = _text(item.get("reason"))

    warnings = []
    for row in rows:
        for key in (
            (row["employee"], row["date"], row["shift"]),
            (row["employee"], row["date"], ""),
        ):
            if key not in blocked:
                continue
            reason = reasons.get(key)
            warnings.append(_warning(
                UNAVAILABLE, SEVERITY_WARNING,
                "%s משובץ ל%s בתאריך %s למרות אילוץ שנרשם%s."
                % (row["employee"], row["shift"], row["date"],
                   " (%s)" % reason if reason else ""),
                employee=row["employee"], date=row["date"], shift=row["shift"],
            ))
            break
    return warnings


def _over_hours(
    rows: List[dict], employees: List[dict], policy: dict
) -> List[dict]:
    """Weekly hours past the ceiling, per person.

    Weeks are ISO weeks off the assignment date rather than the manager's
    planning period: a person's rest does not reset because a new schedule
    started midweek.
    """
    limits = {}
    for employee in employees or []:
        if not isinstance(employee, dict):
            continue
        name = _text(employee.get("name"))
        if not name:
            continue
        limit = _number(employee.get("max_weekly_hours"), 0.0)
        if limit > 0:
            limits[name] = limit

    totals: Dict[tuple, float] = {}
    for row in rows:
        if row["day"] is None:
            continue
        year, week, _ = row["day"].isocalendar()
        key = (row["employee"], year, week)
        totals[key] = totals.get(key, 0.0) + row["hours"]

    warnings = []
    for (employee, year, week), hours in totals.items():
        limit = limits.get(employee, policy["max_weekly_hours"])
        if hours > limit:
            warnings.append(_warning(
                OVER_HOURS, SEVERITY_WARNING,
                "ל%s יש %.1f שעות בשבוע %d/%d, מעל התקרה של %.1f."
                % (employee, hours, week, year, limit),
                employee=employee,
                details={"hours": round(hours, 2), "limit": limit,
                         "week": week, "year": year},
            ))
    return warnings


def _consecutive_days(rows: List[dict], policy: dict) -> List[dict]:
    """Runs of consecutive worked days past the ceiling.

    Counts distinct days: two shifts on one day are one day worked here, and
    the thing that makes them a problem is rest, reported separately.
    """
    days: Dict[str, set] = {}
    for row in rows:
        if row["day"] is not None:
            days.setdefault(row["employee"], set()).add(row["day"])

    limit = policy["max_consecutive_days"]
    warnings = []
    for employee, worked in days.items():
        for run_start, run_length in _runs(sorted(worked)):
            if run_length > limit:
                warnings.append(_warning(
                    CONSECUTIVE, SEVERITY_WARNING,
                    "%s עובד %d ימים ברצף מ-%s, מעל המקסימום של %d."
                    % (employee, run_length, run_start.isoformat(), limit),
                    employee=employee, date=run_start.isoformat(),
                    details={"days": run_length, "limit": limit},
                ))
    return warnings


def _runs(days: List[datetime.date]) -> List[tuple]:
    """(first day, length) for each maximal run of consecutive dates."""
    runs = []
    start = previous = None
    length = 0
    for day in days:
        if previous is not None and (day - previous).days == 1:
            length += 1
        else:
            if start is not None:
                runs.append((start, length))
            start, length = day, 1
        previous = day
    if start is not None:
        runs.append((start, length))
    return runs


def _short_rest(
    rows: List[dict], shift_index: Dict[str, dict], policy: dict
) -> List[dict]:
    """Too little time between the end of one shift and the start of the next.

    Also what catches two shifts that genuinely overlap, which come out as a
    negative gap and are reported as the same class of problem: the person
    cannot be in both.
    """
    minimum = policy["min_rest_hours"]
    by_employee: Dict[str, List[dict]] = {}
    for row in rows:
        if row["day"] is None or row["start"] is None or row["end"] is None:
            continue
        by_employee.setdefault(row["employee"], []).append(row)

    warnings = []
    for employee, worked in by_employee.items():
        ordered = sorted(worked, key=lambda item: _starts_at(item))
        for earlier, later in zip(ordered, ordered[1:]):
            gap = (_starts_at(later) - _ends_at(earlier)).total_seconds() / 3600.0
            if gap < minimum:
                warnings.append(_warning(
                    SHORT_REST, SEVERITY_WARNING,
                    "ל%s יש %.1f שעות מנוחה בין %s ב-%s לבין %s ב-%s, "
                    "פחות מ-%.1f."
                    % (employee, gap, earlier["shift"], earlier["date"],
                       later["shift"], later["date"], minimum),
                    employee=employee, date=later["date"],
                    shift=later["shift"],
                    details={"rest_hours": round(gap, 2), "minimum": minimum},
                ))
    return warnings


def _staffing(
    rows: List[dict], shifts: List[dict], slots: Optional[List[dict]] = None
) -> List[dict]:
    """Slots short of their headcount, and slots over it.

    Understaffing is a warning -- somebody does not show up. Overstaffing is
    a notice: it costs money but nothing breaks, and the manager may have
    done it deliberately for training or cover.

    The set of slots to check comes from the schedule's grid when the caller
    has one, and from the assignments only as a fallback. Deriving it from
    assignments alone would skip any slot with nobody on it at all -- an
    entirely unstaffed shift would report nothing, which is the exact
    situation the manager most needs told about.
    """
    filled: Dict[tuple, int] = {}
    for row in rows:
        key = (row["date"], row["shift"])
        filled[key] = filled.get(key, 0) + 1

    if slots:
        checked = {
            (_text(slot.get("slot_date")) or _iso_date(slot.get("slot_date")),
             _text(slot.get("shift_name")))
            for slot in slots if isinstance(slot, dict)
        }
        checked = {pair for pair in checked if pair[0] and pair[1]}
    else:
        checked = {(row["date"], row["shift"]) for row in rows}

    warnings = []
    for date, shift_name in sorted(checked):
        needed = _headcount_for(shifts, shift_name, _parse_date(date))
        if needed is None:
            continue
        count = filled.get((date, shift_name), 0)
        if count < needed:
            warnings.append(_warning(
                UNFILLED, SEVERITY_WARNING,
                "במשמרת %s בתאריך %s משובצים %d מתוך %d."
                % (shift_name, date, count, needed),
                date=date, shift=shift_name,
                details={"assigned": count, "required": needed},
            ))
        elif count > needed:
            warnings.append(_warning(
                OVERSTAFFED, SEVERITY_NOTICE,
                "במשמרת %s בתאריך %s משובצים %d במקום %d."
                % (shift_name, date, count, needed),
                date=date, shift=shift_name,
                details={"assigned": count, "required": needed},
            ))
    return warnings


def _headcount_for(
    shifts: List[dict], shift_name: str, day: Optional[datetime.date]
) -> Optional[int]:
    """The headcount this shift needs on this day, or None if unstated.

    `staffing` is a list of per-day-group requirements because the interview
    asks whether the standard changes between weekdays. A group naming no
    days is the default for every day the shift runs; a group naming this
    day's Hebrew weekday wins over it.
    """
    for shift in shifts or []:
        if not isinstance(shift, dict) or _text(shift.get("name")) != shift_name:
            continue
        staffing = shift.get("staffing")
        if not isinstance(staffing, list):
            return None
        fallback = None
        weekday = _hebrew_weekday(day)
        for group in staffing:
            if not isinstance(group, dict):
                continue
            days = group.get("days")
            headcount = group.get("headcount")
            if not isinstance(headcount, int):
                continue
            if not isinstance(days, list) or not days:
                fallback = headcount
            elif weekday and weekday in [_text(item) for item in days]:
                return headcount
        return fallback
    return None


# Hebrew weekday names, matching how the interview and the source files write
# them. Hebrew is data here, not presentation ([FILE_FORMATS.md]).
_HEBREW_WEEKDAYS = (
    "יום שני", "יום שלישי", "יום רביעי", "יום חמישי",
    "יום שישי", "שבת", "יום ראשון",
)


def _hebrew_weekday(day: Optional[datetime.date]) -> str:
    """`day`'s Hebrew name. `weekday()` is Monday-based; the tuple matches."""
    if day is None:
        return ""
    return _HEBREW_WEEKDAYS[day.weekday()]


def _starts_at(row: dict) -> datetime.datetime:
    return datetime.datetime.combine(row["day"], row["start"].time())


def _ends_at(row: dict) -> datetime.datetime:
    """The end instant, rolled to the next day when the shift crosses midnight."""
    end = datetime.datetime.combine(row["day"], row["end"].time())
    if row["end"] <= row["start"]:
        end += datetime.timedelta(days=1)
    return end


def _warning(
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


def _iso_date(value: Any) -> str:
    """A slot date as an ISO string, however the row carried it.

    Repository rows come back as `datetime.date`; a caller building a grid in
    memory passes strings. Both are compared against assignment dates here.
    """
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return ""


def _parse_date(value: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _parse_time(value: Any) -> Optional[datetime.datetime]:
    """`HH:MM` as a datetime on a fixed day, for arithmetic only.

    A shift with an unparseable time contributes no hours and no rest check
    rather than a guessed one -- `audit.py` reporting a number it invented
    would defeat the entire reason it is not the model doing this.
    """
    text = _text(value)
    if not text:
        return None
    for shape in ("%H:%M", "%H:%M:%S", "%H"):
        try:
            parsed = datetime.datetime.strptime(text, shape)
            return parsed.replace(year=2000, month=1, day=1)
        except ValueError:
            continue
    return None


def _number(value: Any, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "audit", "OVER_HOURS", "CONSECUTIVE", "SHORT_REST", "DOUBLE_BOOKED",
    "UNAVAILABLE", "UNFILLED", "OVERSTAFFED",
    "SEVERITY_WARNING", "SEVERITY_NOTICE",
]
