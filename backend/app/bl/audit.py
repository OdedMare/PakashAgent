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
MISSING_ROLE = "missing_role"
MISSING_COMMANDER = "missing_commander"

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
# Friday and Saturday: the Israeli weekend, matching how the interview
# collects a shift's `days` and how the real files are written.
_WEEKEND_WEEKDAYS = frozenset({4, 5})


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
    warnings.extend(_staffing(
        rows, shifts or [], employees or [], profile or {}, slots
    ))
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


def personal_summary(
    employee: str,
    assignments: List[dict],
    shifts: List[dict],
    warnings: Optional[List[dict]] = None,
    availability: Optional[List[dict]] = None,
) -> dict:
    """One person's own totals: hours, shifts, and the warnings about them.

    Added for the employee's personal area
    ([D14](../../../docs/DECISIONS.md#d14--employees-get-real-identities-and-may-submit-constraints-️-reverses-d5-amends-d10)),
    and put *here* rather than in `bl/` for one reason: it must reuse
    `_shift_hours`, the same weighted arithmetic the warnings are computed
    from. A second hours calculation elsewhere would eventually disagree with
    this one, and an employee reading 38 where their manager reads 41 is worse
    than showing nothing at all.

    The on-call split is broken out because it is the number that surprises
    people. `כונן לילה` in one of the real files counts at a weight the
    interview collects (D9), so an eight-hour on-call may count as four --
    which looks like a mistake unless the breakdown says so plainly.

    Still no model call and still no authority: this reports, exactly as the
    rest of the module does.
    """
    name = _text(employee)
    shift_index = _index_shifts(shifts)
    rows = [_row(item, shift_index) for item in assignments or []]
    rows = [
        row for row in rows if row is not None and row["employee"] == name
    ]
    rows.sort(key=lambda row: (row["date"], row["shift"]))

    total = round(sum(row["hours"] for row in rows), 2)
    on_call_rows = [row for row in rows if row["is_on_call"]]
    on_call_hours = round(sum(row["hours"] for row in on_call_rows), 2)

    by_shift: Dict[str, dict] = {}
    for row in rows:
        entry = by_shift.setdefault(
            row["shift"], {"shift": row["shift"], "count": 0, "hours": 0.0}
        )
        entry["count"] += 1
        entry["hours"] = round(entry["hours"] + row["hours"], 2)

    weeks: Dict[str, float] = {}
    for row in rows:
        if row["day"] is None:
            continue
        year, week, _ = row["day"].isocalendar()
        key = "%d-W%02d" % (year, week)
        weeks[key] = round(weeks.get(key, 0.0) + row["hours"], 2)

    return {
        "employee": name,
        "total_hours": total,
        "shift_count": len(rows),
        "days_worked": len(set(row["date"] for row in rows)),
        # Split out so a weighted on-call total reads as intentional rather
        # than as arithmetic gone wrong.
        "on_call_count": len(on_call_rows),
        "on_call_hours": on_call_hours,
        "worked_hours": round(total - on_call_hours, 2),
        "by_shift": sorted(by_shift.values(), key=lambda item: item["shift"]),
        "by_week": [
            {"week": key, "hours": weeks[key]} for key in sorted(weeks)
        ],
        "shifts": [
            {
                "date": row["date"],
                "shift": row["shift"],
                "hours": row["hours"],
                "is_on_call": row["is_on_call"],
                "weekday": _hebrew_weekday(row["day"]),
            }
            for row in rows
        ],
        # Only the warnings naming this person. A team-wide warning
        # (`unfilled`, `overstaffed`) carries no employee and is deliberately
        # not shown here: it is the manager's problem, and surfacing it in a
        # personal view invites someone to read it as being about them.
        "warnings": [
            item for item in (warnings or [])
            if _text(item.get("employee")) == name
        ],
        "constraints": [
            item for item in (availability or [])
            if _text(item.get("employee")) == name
        ],
    }


def fairness(
    assignments: List[dict], shifts: List[dict], employees: List[dict]
) -> dict:
    """Hours per person against the team average.

    The number that answers "why is it always me". It is arithmetic over the
    same rows the audit already walks, so it is honest by construction -- and
    it is a *report*, not a rule: nothing here says a schedule is unfair, only
    what the totals are.

    Everyone on the roster appears, including people with no shifts at all.
    Dropping them would hide the most significant case the comparison exists
    to reveal.
    """
    shift_index = _index_shifts(shifts)
    rows = [_row(item, shift_index) for item in assignments or []]
    rows = [row for row in rows if row is not None]

    totals: Dict[str, float] = {}
    for employee in employees or []:
        name = _text(
            employee.get("name") if isinstance(employee, dict) else employee
        )
        if name:
            totals.setdefault(name, 0.0)
    for row in rows:
        totals[row["employee"]] = round(
            totals.get(row["employee"], 0.0) + row["hours"], 2
        )

    values = list(totals.values())
    average = round(sum(values) / len(values), 2) if values else 0.0
    return {
        "average_hours": average,
        "people": sorted(
            [
                {
                    "employee": name,
                    "hours": hours,
                    "delta": round(hours - average, 2),
                }
                for name, hours in totals.items()
            ],
            key=lambda item: (-item["hours"], item["employee"]),
        ),
    }


def load_history(
    assignments: List[dict],
    shifts: List[dict],
    employees: List[dict],
) -> List[dict]:
    """How much each person has carried across *past* periods.

    The other side of `fairness()`. That one compares hours inside the period
    on screen; this one looks backwards, at who has been taking the nights and
    the weekends, and is what the scheduler reasons from when it decides whose
    turn the next one is.

    It exists because the scheduler used to be handed several hundred raw
    assignment rows and left to count them itself. That is wrong twice: on a
    two-week period the rows were roughly 60% of the whole prompt, crowding out
    the period actually being built, and counting is the one thing
    [D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)
    puts on this side of the line. A model asked "who has worked the most
    nights" is doing arithmetic by generation, and a wrong answer there looks
    exactly like a right one.

    Nothing here decides anything. It reports that Ron has six nights and Dana
    none; whether that means Dana takes the next one is the model's call.

    Everyone on the roster appears, zeros included -- for the same reason
    `fairness()` keeps them. A person with no nights yet is the most useful row
    in the table, and an absent row reads as missing data rather than as zero.
    """
    shift_index = _index_shifts(shifts)
    rows = [_row(item, shift_index) for item in assignments or []]
    rows = [row for row in rows if row is not None]

    totals: Dict[str, dict] = {}
    for employee in employees or []:
        name = _text(
            employee.get("name") if isinstance(employee, dict) else employee
        )
        if name:
            totals.setdefault(name, _empty_load())
    for row in rows:
        # A name the roster no longer lists -- someone who left, or a spelling
        # that changed. Kept, because dropping it would understate how much of
        # the load the people still here actually carried.
        entry = totals.setdefault(row["employee"], _empty_load())
        entry["shifts"] += 1
        entry["hours"] = round(entry["hours"] + row["hours"], 2)
        if row["is_on_call"] or _is_night(shift_index.get(row["shift"])):
            entry["nights"] += 1
        if row["day"] is not None and row["day"].weekday() in _WEEKEND_WEEKDAYS:
            entry["weekends"] += 1
        if row["date"] > entry["last_worked"]:
            entry["last_worked"] = row["date"]

    return sorted(
        [dict(counts, employee=name) for name, counts in totals.items()],
        key=lambda item: (-item["nights"], -item["hours"], item["employee"]),
    )


def _is_night(shift: Optional[dict]) -> bool:
    """Whether the vocabulary marks this shift as a night.

    Read off the shift definition, never inferred from its name or its start
    time: the vocabulary is per-workplace
    ([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)),
    so a guess here would be the hardcoding that decision forbids. A workplace
    that never flags a night simply reports zero nights, which is honest --
    unlike a number produced by matching against a list of names nobody
    declared.
    """
    if not isinstance(shift, dict):
        return False
    return bool(shift.get("is_night") or shift.get("is_overnight"))


def _empty_load() -> dict:
    return {
        "shifts": 0, "hours": 0.0, "nights": 0,
        "weekends": 0, "last_worked": "",
    }


def shift_stats(
    assignments: List[dict],
    shifts: List[dict],
    employees: List[dict],
    slots: Optional[List[dict]] = None,
    warnings: Optional[List[dict]] = None,
    availability: Optional[List[dict]] = None,
) -> dict:
    """The period in numbers: coverage, load, distribution, and pressure.

    The manager's counterpart to `personal_summary` -- one person's totals
    turned around to face the whole roster. It is here rather than in `bl/`
    for the same reason that one is: it must reuse `_shift_hours`, so the
    hours a chart draws and the hours a warning names are the same
    arithmetic. A second calculation feeding the graphs would eventually
    disagree with the audit, and a bar chart that contradicts the warning
    printed under it is worse than no chart.

    Still a report and still no authority
    ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
    Nothing here is a target, a quota, or a threshold the schedule is graded
    against. `coverage` counts filled slots against the headcount the shifts
    ask for; it does not say a schedule is unacceptable at 80%.

    Everyone on the roster appears in `by_employee`, including people with no
    shifts at all -- the zero is the most informative bar on the chart, and
    dropping it would hide exactly the person the manager is looking for.
    """
    shift_index = _index_shifts(shifts)
    rows = [_row(item, shift_index) for item in assignments or []]
    rows = [row for row in rows if row is not None]

    return {
        "total_hours": round(sum(row["hours"] for row in rows), 2),
        "total_shifts": len(rows),
        "people_working": len(set(row["employee"] for row in rows)),
        "coverage": _coverage(rows, shifts or [], slots),
        "by_shift": _stats_by_shift(rows, shift_index),
        "by_day": _stats_by_day(rows, slots),
        "by_employee": _stats_by_employee(rows, employees or []),
        "warning_counts": _warning_counts(warnings or []),
        "constraint_pressure": _constraint_pressure(
            rows, availability or []
        ),
    }


def _coverage(
    rows: List[dict], shifts: List[dict], slots: Optional[List[dict]]
) -> dict:
    """Filled seats against required seats, over the period's grid.

    Counted in *seats*, not slots: a shift needing three people with two on
    it is two thirds covered, and rounding that up to "filled" would hide the
    understaffing the manager most wants to see. Slots whose headcount the
    profile does not state are left out of both halves rather than assumed to
    need one -- an invented denominator would make the percentage fiction.
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
        checked = set(filled)

    required = 0
    assigned = 0
    unfilled_slots = 0
    for date, shift_name in checked:
        needed = _headcount_for(shifts, shift_name, _parse_date(date))
        if needed is None:
            continue
        count = filled.get((date, shift_name), 0)
        required += needed
        assigned += min(count, needed)
        if count < needed:
            unfilled_slots += 1

    return {
        "required": required,
        "assigned": assigned,
        "unfilled_slots": unfilled_slots,
        # Guarded because a period whose shifts state no headcount has a
        # required of zero, and "0 filled of 0" is 100% covered, not an error.
        "percent": round(assigned / required * 100, 1) if required else 100.0,
    }


def _stats_by_shift(
    rows: List[dict], shift_index: Dict[str, dict]
) -> List[dict]:
    """Load per shift name, in the workplace's own vocabulary (D9).

    Every shift the vocabulary declares appears, whether or not anyone was
    put on it. A named shift missing from the chart reads as "no such shift"
    when it actually means "nobody scheduled" -- opposite meanings.
    """
    totals: Dict[str, dict] = {}
    for name, shift in shift_index.items():
        totals[name] = {
            "shift": name,
            "count": 0,
            "hours": 0.0,
            "is_on_call": bool(shift.get("is_on_call")),
        }
    for row in rows:
        entry = totals.setdefault(
            row["shift"],
            {"shift": row["shift"], "count": 0, "hours": 0.0,
             "is_on_call": row["is_on_call"]},
        )
        entry["count"] += 1
        entry["hours"] = round(entry["hours"] + row["hours"], 2)
    return sorted(totals.values(), key=lambda item: item["shift"])


def _stats_by_day(rows: List[dict], slots: Optional[List[dict]]) -> List[dict]:
    """Headcount and hours per date, ordered as the period runs.

    Dates come from the grid where there is one, so a day nobody was
    scheduled on is a visible zero rather than a gap the chart closes up.
    """
    days: Dict[str, dict] = {}

    def entry(date: str) -> dict:
        return days.setdefault(
            date,
            {
                "date": date,
                "weekday": _hebrew_weekday(_parse_date(date)),
                "count": 0,
                "hours": 0.0,
                "on_call": 0,
            },
        )

    for slot in slots or []:
        if not isinstance(slot, dict):
            continue
        date = _text(slot.get("slot_date")) or _iso_date(slot.get("slot_date"))
        if date:
            entry(date)
    for row in rows:
        item = entry(row["date"])
        item["count"] += 1
        item["hours"] = round(item["hours"] + row["hours"], 2)
        if row["is_on_call"]:
            item["on_call"] += 1

    return [days[key] for key in sorted(days)]


def _stats_by_employee(rows: List[dict], employees: List[dict]) -> List[dict]:
    """Per-person load, heaviest first, with everyone on the roster present.

    The same numbers `fairness` reports, plus the shift and on-call counts
    behind them -- so the chart can show *why* two people on equal hours are
    not carrying an equal week.
    """
    totals: Dict[str, dict] = {}

    def entry(name: str) -> dict:
        return totals.setdefault(
            name,
            {
                "employee": name,
                "hours": 0.0,
                "shifts": 0,
                "on_call": 0,
                "days": 0,
            },
        )

    for employee in employees or []:
        name = _text(
            employee.get("name") if isinstance(employee, dict) else employee
        )
        if name:
            entry(name)

    worked_days: Dict[str, set] = {}
    for row in rows:
        item = entry(row["employee"])
        item["hours"] = round(item["hours"] + row["hours"], 2)
        item["shifts"] += 1
        if row["is_on_call"]:
            item["on_call"] += 1
        worked_days.setdefault(row["employee"], set()).add(row["date"])

    for name, dates in worked_days.items():
        totals[name]["days"] = len(dates)

    return sorted(
        totals.values(),
        key=lambda item: (-item["hours"], item["employee"]),
    )


def _warning_counts(warnings: List[dict]) -> List[dict]:
    """How many findings of each kind, most first.

    Presentation of a count, not a score. A period with six overstaffing
    notices is not "worse" than one with a single double-booking, and nothing
    here totals them into a number that would imply it does.
    """
    counts: Dict[str, dict] = {}
    for item in warnings or []:
        if not isinstance(item, dict):
            continue
        code = _text(item.get("code"))
        if not code:
            continue
        entry = counts.setdefault(
            code,
            {
                "code": code,
                "severity": _text(item.get("severity")) or SEVERITY_NOTICE,
                "count": 0,
            },
        )
        entry["count"] += 1
    return sorted(
        counts.values(),
        key=lambda item: (
            0 if item["severity"] == SEVERITY_WARNING else 1,
            -item["count"],
            item["code"],
        ),
    )


def _constraint_pressure(
    rows: List[dict], availability: List[dict]
) -> dict:
    """How constrained the period was, and how often that was overridden.

    `blocked` counts recorded unavailability inside the period; `honored` is
    how much of it the schedule respected. It answers the question a manager
    asks after a hard week -- "how much were we working around?" -- which the
    warning list cannot, because a constraint that was honored produces no
    warning and so leaves no trace there at all.
    """
    blocked = 0
    conflicts = 0
    people = set()
    for item in availability or []:
        if not isinstance(item, dict):
            continue
        employee = _text(item.get("employee"))
        date = _text(item.get("date"))
        if not employee or not date:
            continue
        # A positive row with no window merely says "available" and does not
        # narrow any choice. A positive time window does: for example, from
        # 16:00 onward.
        if item.get("available") and not (
            _text(item.get("start_time")) or _text(item.get("end_time"))
        ):
            continue
        blocked += 1
        people.add(employee)
        if any(constraint_conflicts(row, item) for row in rows):
            conflicts += 1

    return {
        "blocked": blocked,
        "people": len(people),
        "conflicts": conflicts,
        "honored": blocked - conflicts,
    }


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
    """Assignments that contradict hard or soft availability windows."""
    warnings = []
    for row in rows:
        for item in availability or []:
            if not constraint_conflicts(row, item):
                continue
            reason = _text(item.get("reason"))
            hard = item.get("is_hard", True) is not False
            window = _constraint_window(item)
            warnings.append(_warning(
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
                    "start_time": _text(item.get("start_time")),
                    "end_time": _text(item.get("end_time")),
                },
            ))
            break
    return warnings


def constraint_conflicts(assignment: dict, constraint: dict) -> bool:
    """Whether one assignment falls outside one recorded availability.

    The same arithmetic feeds candidate filtering and the advisory audit.
    `available=True` plus times means the employee may work only inside that
    window; `available=False` plus times means that window itself is blocked.
    With no times, the old whole-day/whole-shift behaviour is preserved.
    """
    if not isinstance(assignment, dict) or not isinstance(constraint, dict):
        return False
    if _text(assignment.get("employee")) != _text(constraint.get("employee")):
        return False
    if _text(assignment.get("date")) != _text(
        constraint.get("date") or constraint.get("constraint_date")
    ):
        return False
    constrained_shift = _text(
        constraint.get("shift") or constraint.get("shift_name")
    )
    if constrained_shift and constrained_shift != _text(assignment.get("shift")):
        return False

    start_bound = _minutes(constraint.get("start_time"))
    end_bound = _minutes(constraint.get("end_time"))
    if start_bound is None and end_bound is None:
        return not bool(constraint.get("available"))

    shift_start = _minutes(assignment.get("start") or assignment.get("start_time"))
    shift_end = _minutes(assignment.get("end") or assignment.get("end_time"))
    # A timed constraint cannot be evaluated against a shift whose hours the
    # workplace never defined. Leave it visible to the model rather than
    # pretending the unknown hours are a conflict.
    if shift_start is None or shift_end is None:
        return False
    if shift_end <= shift_start:
        shift_end += 24 * 60

    if constraint.get("available"):
        window_end = end_bound
        if start_bound is not None and window_end is not None and window_end <= start_bound:
            window_end += 24 * 60
        return (
            (start_bound is not None and shift_start < start_bound)
            or (window_end is not None and shift_end > window_end)
        )

    blocked_start = start_bound if start_bound is not None else 0
    blocked_end = end_bound if end_bound is not None else 24 * 60
    if start_bound is not None and end_bound is not None and blocked_end <= blocked_start:
        blocked_end += 24 * 60
    return shift_start < blocked_end and blocked_start < shift_end


def _constraint_window(item: dict) -> str:
    start = _text(item.get("start_time"))
    end = _text(item.get("end_time"))
    if start and end:
        return "%s–%s" % (start, end)
    if start:
        return "החל מ-%s" % start
    if end:
        return "עד %s" % end
    return ""


def _minutes(value: Any) -> Optional[int]:
    if isinstance(value, datetime.datetime):
        return value.hour * 60 + value.minute
    if isinstance(value, datetime.time):
        return value.hour * 60 + value.minute
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return parsed.hour * 60 + parsed.minute


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
    rows: List[dict], shifts: List[dict], employees: List[dict], profile: dict,
    slots: Optional[List[dict]] = None,
) -> List[dict]:
    """Slots short of headcount or required roles, and slots over headcount.

    Understaffing is a warning -- somebody does not show up. Overstaffing is
    a notice: it costs money but nothing breaks, and the manager may have
    done it deliberately for training or cover.

    The set of slots to check comes from the schedule's grid when the caller
    has one, and from the assignments only as a fallback. Deriving it from
    assignments alone would skip any slot with nobody on it at all -- an
    entirely unstaffed shift would report nothing, which is the exact
    situation the manager most needs told about.
    """
    employee_index = {
        _text(person.get("name")): person
        for person in employees or []
        if isinstance(person, dict) and _text(person.get("name"))
    }
    training_policy = profile.get("training_policy")
    training_policy = training_policy if isinstance(training_policy, dict) else {}
    counted_rows = []
    for row in rows:
        person = employee_index.get(row["employee"], {})
        explicit = person.get("counts_toward_staffing")
        counts = explicit if isinstance(explicit, bool) else not bool(
            person.get("is_trainee")
        ) or bool(training_policy.get("counts_toward_staffing"))
        if counts:
            counted_rows.append(row)

    filled: Dict[tuple, int] = {}
    filled_roles: Dict[tuple, set] = {}
    commanded = {
        (row["date"], row["shift"])
        for row in rows
        if employee_index.get(row["employee"], {}).get("is_shift_manager")
    }
    for row in counted_rows:
        key = (row["date"], row["shift"])
        filled[key] = filled.get(key, 0) + 1
        person = employee_index.get(row["employee"], {})
        roles = person.get("roles")
        if not isinstance(roles, list):
            roles = [person.get("role")]
        filled_roles.setdefault(key, set()).update(
            _text(role) for role in roles if _text(role)
        )

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
        required_roles = _required_roles_for(
            shifts, shift_name, _parse_date(date), slots
        )
        present = filled_roles.get((date, shift_name), set())
        for role in required_roles:
            if role in present:
                continue
            warnings.append(_warning(
                MISSING_ROLE, SEVERITY_WARNING,
                "במשמרת %s בתאריך %s חסר התפקיד הנדרש %s."
                % (shift_name, date, role),
                date=date, shift=shift_name,
                details={"required_role": role},
            ))
        if _requires_shift_manager(shifts, shift_name, date, slots) \
                and (date, shift_name) not in commanded:
            warnings.append(_warning(
                MISSING_COMMANDER, SEVERITY_WARNING,
                "במשמרת %s בתאריך %s חסר/ה מפקד/ת משמרת מוסמך/ת."
                % (shift_name, date),
                date=date, shift=shift_name,
                details={"requires_shift_manager": True},
            ))
    return warnings


def _requires_shift_manager(
    shifts: List[dict], shift_name: str, date: str,
    slots: Optional[List[dict]] = None,
) -> bool:
    for slot in slots or []:
        if not isinstance(slot, dict):
            continue
        slot_date = _text(slot.get("slot_date")) or _iso_date(
            slot.get("slot_date")
        )
        if slot_date == date and _text(slot.get("shift_name")) == shift_name:
            return bool(slot.get("requires_shift_manager"))
    for shift in shifts or []:
        if isinstance(shift, dict) and _text(shift.get("name")) == shift_name:
            return bool(shift.get("requires_shift_manager"))
    return False


def _required_roles_for(
    shifts: List[dict], shift_name: str, day: Optional[datetime.date],
    slots: Optional[List[dict]] = None,
) -> List[str]:
    """Required roles copied onto the slot, with profile fallback."""
    date = day.isoformat() if day else ""
    for slot in slots or []:
        if not isinstance(slot, dict):
            continue
        slot_date = _text(slot.get("slot_date")) or _iso_date(
            slot.get("slot_date")
        )
        if slot_date != date or _text(slot.get("shift_name")) != shift_name:
            continue
        roles = slot.get("required_roles")
        if isinstance(roles, list):
            return [_text(role) for role in roles if _text(role)]

    weekday = _weekday_key(_hebrew_weekday(day))
    for shift in shifts or []:
        if not isinstance(shift, dict) or _text(shift.get("name")) != shift_name:
            continue
        fallback: List[str] = []
        for group in shift.get("staffing") or []:
            if not isinstance(group, dict):
                continue
            roles = group.get("required_roles")
            roles = [_text(role) for role in roles or [] if _text(role)] \
                if isinstance(roles, list) else []
            days = group.get("days")
            if not isinstance(days, list) or not days:
                fallback = roles
            elif weekday and weekday in {_weekday_key(_text(item)) for item in days}:
                return roles
        return fallback
    return []


def _weekday_key(value: str) -> str:
    value = _text(value)
    return value[4:].strip() if value.startswith("יום ") else value


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
    "audit", "personal_summary", "fairness", "load_history", "shift_stats",
    "OVER_HOURS", "CONSECUTIVE", "SHORT_REST", "DOUBLE_BOOKED",
    "UNAVAILABLE", "UNFILLED", "OVERSTAFFED", "MISSING_ROLE",
    "MISSING_COMMANDER",
    "SEVERITY_WARNING", "SEVERITY_NOTICE",
]
