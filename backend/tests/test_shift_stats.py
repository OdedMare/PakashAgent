"""The period in numbers, as the control room's charts read it.

Table-driven for the same reason `test_audit.py` and
`test_personal_summary.py` are: these numbers are the entire product of the
function, a chart drawn from a wrong one looks exactly like a chart drawn
from a right one, and the manager has no way to check it by eye.

Two properties here are worth more than the rest, and each has its own test:

- **The stats reuse the audit's arithmetic.** `test_stats_hours_match_*`
  pins a chart's hours against `personal_summary` and `fairness` over the
  same roster. If those ever diverge, a bar disagrees with the warning
  printed underneath it -- which is worse than drawing no chart at all.
- **Absent things are present as zeros.** A person with no shifts, a declared
  shift nobody was put on, and a day nobody worked all have to appear. Each
  is the most informative mark on its chart, and dropping it turns "nobody
  scheduled" into "no such thing" -- opposite meanings.
"""

from app.bl.audit import fairness, personal_summary, shift_stats

# This workplace's own vocabulary, never known in advance (D9).
MORNING = "בוקר"
EVENING = "צהריים"
ON_CALL = "כונן לילה"

SHIFTS = [
    {"name": MORNING, "start_time": "07:00", "end_time": "15:00",
     "is_on_call": False, "hour_weight": 1.0,
     "staffing": [{"headcount": 2}]},
    {"name": EVENING, "start_time": "15:00", "end_time": "23:00",
     "is_on_call": False, "hour_weight": 1.0,
     "staffing": [{"headcount": 1}]},
    # Available rather than working: the interview collected the weight and
    # the audit applies it, so an 8-hour on-call counts as 4.
    {"name": ON_CALL, "start_time": "23:00", "end_time": "07:00",
     "is_on_call": True, "hour_weight": 0.5,
     "staffing": [{"headcount": 1}]},
]

DANA = "דנה"
YOSSI = "יוסי"
RON = "רון"
EMPLOYEES = [{"name": DANA}, {"name": YOSSI}, {"name": RON}]

MONDAY = "2026-03-02"
TUESDAY = "2026-03-03"


def _assignment(employee, shift, date):
    return {"employee": employee, "shift": shift, "date": date}


def _slot(shift, date):
    return {"shift_name": shift, "slot_date": date}


# --- the totals -------------------------------------------------------------

def test_totals_count_the_whole_period():
    rows = [
        _assignment(DANA, MORNING, MONDAY),
        _assignment(YOSSI, MORNING, MONDAY),
        _assignment(RON, ON_CALL, MONDAY),
    ]

    stats = shift_stats(rows, SHIFTS, EMPLOYEES)

    assert stats["total_shifts"] == 3
    assert stats["people_working"] == 3
    # 8 + 8 morning, plus an on-call weighted to 4.
    assert stats["total_hours"] == 20.0


def test_an_empty_period_is_zeros_rather_than_an_error():
    """The state the screen opens in before anything is built.

    The panel renders whatever this returns, so the no-schedule case has to
    be a shape rather than an exception.
    """
    stats = shift_stats([], SHIFTS, EMPLOYEES)

    assert stats["total_hours"] == 0.0
    assert stats["total_shifts"] == 0
    assert stats["people_working"] == 0
    # Everyone still appears, all on zero -- see the by-employee tests.
    assert len(stats["by_employee"]) == 3


# --- coverage ---------------------------------------------------------------

def test_coverage_counts_seats_not_slots():
    """A shift needing two people with one on it is half covered.

    Counting slots instead would round that up to "filled" and hide the
    understaffing entirely, which is the case the manager most needs to see.
    """
    slots = [_slot(MORNING, MONDAY)]
    rows = [_assignment(DANA, MORNING, MONDAY)]

    coverage = shift_stats(rows, SHIFTS, EMPLOYEES, slots=slots)["coverage"]

    assert coverage["required"] == 2
    assert coverage["assigned"] == 1
    assert coverage["percent"] == 50.0
    assert coverage["unfilled_slots"] == 1


def test_coverage_sees_a_slot_nobody_is_on():
    """The unstaffed shift, which leaves no assignment row to notice.

    Same trap `audit()` documents for the unfilled warning: derived from the
    assignments alone, an entirely empty slot is invisible.
    """
    slots = [_slot(MORNING, MONDAY), _slot(EVENING, MONDAY)]
    rows = [
        _assignment(DANA, MORNING, MONDAY),
        _assignment(YOSSI, MORNING, MONDAY),
    ]

    coverage = shift_stats(rows, SHIFTS, EMPLOYEES, slots=slots)["coverage"]

    assert coverage["required"] == 3
    assert coverage["assigned"] == 2
    assert coverage["unfilled_slots"] == 1


def test_overstaffing_does_not_push_coverage_past_full():
    """Three people on a two-person shift is 100%, not 150%.

    The extra body is a notice from the audit, not coverage of a seat that
    does not exist.
    """
    slots = [_slot(MORNING, MONDAY)]
    rows = [
        _assignment(DANA, MORNING, MONDAY),
        _assignment(YOSSI, MORNING, MONDAY),
        _assignment(RON, MORNING, MONDAY),
    ]

    coverage = shift_stats(rows, SHIFTS, EMPLOYEES, slots=slots)["coverage"]

    assert coverage["assigned"] == 2
    assert coverage["percent"] == 100.0


def test_coverage_is_full_when_no_headcount_is_stated():
    """A profile that never said how many people a shift needs.

    Assuming one would invent the denominator, and the percentage would be a
    number the manager could not trace to anything they told the app.
    """
    shifts = [{"name": MORNING, "start_time": "07:00", "end_time": "15:00"}]
    coverage = shift_stats(
        [], shifts, EMPLOYEES, slots=[_slot(MORNING, MONDAY)]
    )["coverage"]

    assert coverage["required"] == 0
    assert coverage["percent"] == 100.0


# --- the breakdowns ---------------------------------------------------------

def test_every_declared_shift_appears_even_with_nobody_on_it():
    """A missing bar would read as "no such shift" rather than "nobody"."""
    rows = [_assignment(DANA, MORNING, MONDAY)]

    by_shift = shift_stats(rows, SHIFTS, EMPLOYEES)["by_shift"]

    assert [row["shift"] for row in by_shift] == sorted(
        [MORNING, EVENING, ON_CALL]
    )
    empty = [row for row in by_shift if row["shift"] == EVENING][0]
    assert empty["count"] == 0
    assert empty["hours"] == 0.0


def test_on_call_is_flagged_so_a_short_bar_reads_as_intentional():
    """Four hours against eight is `hour_weight`, not arithmetic gone wrong."""
    rows = [_assignment(RON, ON_CALL, MONDAY)]

    row = [
        item for item in shift_stats(rows, SHIFTS, EMPLOYEES)["by_shift"]
        if item["shift"] == ON_CALL
    ][0]

    assert row["hours"] == 4.0
    assert row["is_on_call"] is True


def test_everyone_on_the_roster_appears_including_the_unscheduled():
    """The zero bar is the person the manager is looking for."""
    rows = [_assignment(DANA, MORNING, MONDAY)]

    by_employee = shift_stats(rows, SHIFTS, EMPLOYEES)["by_employee"]

    assert len(by_employee) == 3
    idle = [row for row in by_employee if row["employee"] == RON][0]
    assert idle["hours"] == 0.0
    assert idle["shifts"] == 0


def test_employees_are_ordered_heaviest_first():
    rows = [
        _assignment(DANA, MORNING, MONDAY),
        _assignment(DANA, MORNING, TUESDAY),
        _assignment(YOSSI, MORNING, MONDAY),
    ]

    by_employee = shift_stats(rows, SHIFTS, EMPLOYEES)["by_employee"]

    assert [row["employee"] for row in by_employee][:2] == [DANA, YOSSI]
    assert by_employee[0]["hours"] == 16.0
    assert by_employee[0]["days"] == 2


def test_two_shifts_in_one_day_is_one_day_worked():
    """Days and shifts are different counts, and the panel shows both."""
    rows = [
        _assignment(DANA, MORNING, MONDAY),
        _assignment(DANA, EVENING, MONDAY),
    ]

    row = shift_stats(rows, SHIFTS, EMPLOYEES)["by_employee"][0]

    assert row["shifts"] == 2
    assert row["days"] == 1


def test_a_day_nobody_worked_is_a_zero_rather_than_a_gap():
    """Closing the gap would draw a week that looks fully staffed."""
    slots = [_slot(MORNING, MONDAY), _slot(MORNING, TUESDAY)]
    rows = [_assignment(DANA, MORNING, MONDAY)]

    by_day = shift_stats(rows, SHIFTS, EMPLOYEES, slots=slots)["by_day"]

    assert [row["date"] for row in by_day] == [MONDAY, TUESDAY]
    assert by_day[1]["count"] == 0


def test_days_carry_their_hebrew_weekday():
    by_day = shift_stats(
        [_assignment(DANA, MORNING, MONDAY)], SHIFTS, EMPLOYEES
    )["by_day"]

    assert by_day[0]["weekday"] == "יום שני"


# --- warnings and constraint pressure ---------------------------------------

def test_warnings_are_grouped_by_code_most_severe_first():
    warnings = [
        {"code": "overstaffed", "severity": "notice"},
        {"code": "overstaffed", "severity": "notice"},
        {"code": "unfilled", "severity": "warning"},
    ]

    counts = shift_stats(
        [], SHIFTS, EMPLOYEES, warnings=warnings
    )["warning_counts"]

    # Severity orders ahead of count: one real warning outranks two notices.
    assert counts[0]["code"] == "unfilled"
    assert counts[1]["count"] == 2


def test_a_honored_constraint_is_counted_though_it_raised_no_warning():
    """The figure the warning list structurally cannot provide.

    A constraint the schedule respected produces no warning, so "how much
    were we working around this week" is unanswerable from warnings alone.
    """
    availability = [
        {"employee": RON, "date": MONDAY, "shift": "", "available": False},
    ]
    rows = [_assignment(DANA, MORNING, MONDAY)]

    pressure = shift_stats(
        rows, SHIFTS, EMPLOYEES, availability=availability
    )["constraint_pressure"]

    assert pressure["blocked"] == 1
    assert pressure["people"] == 1
    assert pressure["conflicts"] == 0
    assert pressure["honored"] == 1


def test_an_overridden_constraint_is_counted_as_a_conflict():
    availability = [
        {"employee": DANA, "date": MONDAY, "shift": "", "available": False},
    ]
    rows = [_assignment(DANA, MORNING, MONDAY)]

    pressure = shift_stats(
        rows, SHIFTS, EMPLOYEES, availability=availability
    )["constraint_pressure"]

    assert pressure["conflicts"] == 1
    assert pressure["honored"] == 0


def test_availability_rows_are_ignored(): 
    """A row saying someone *is* available is not pressure.

    Only `available: False` constrains anything; counting the rest would
    inflate the figure with information that constrained nothing.
    """
    availability = [
        {"employee": DANA, "date": MONDAY, "shift": "", "available": True},
    ]

    pressure = shift_stats(
        [], SHIFTS, EMPLOYEES, availability=availability
    )["constraint_pressure"]

    assert pressure["blocked"] == 0


# --- the property that matters most -----------------------------------------

def test_stats_hours_match_the_audits_own_arithmetic():
    """One calculation, three readers.

    The manager's chart, the employee's personal total, and the fairness
    comparison all have to be the same number over the same roster. This is
    the test that fails if a second hours implementation ever creeps in --
    which is the whole reason `shift_stats` lives in `audit.py` rather than
    in `bl/` beside the code that renders it.
    """
    rows = [
        _assignment(DANA, MORNING, MONDAY),
        _assignment(DANA, ON_CALL, TUESDAY),
        _assignment(YOSSI, EVENING, MONDAY),
    ]

    stats = shift_stats(rows, SHIFTS, EMPLOYEES)
    personal = personal_summary(DANA, rows, SHIFTS)
    comparison = fairness(rows, SHIFTS, EMPLOYEES)

    charted = [
        row for row in stats["by_employee"] if row["employee"] == DANA
    ][0]
    compared = [
        row for row in comparison["people"] if row["employee"] == DANA
    ][0]

    assert charted["hours"] == personal["total_hours"] == compared["hours"]
    # And the period total is the sum of the people on it.
    assert stats["total_hours"] == round(
        sum(row["hours"] for row in stats["by_employee"]), 2
    )
