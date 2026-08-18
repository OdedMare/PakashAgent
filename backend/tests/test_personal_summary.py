"""One person's own totals, and the fairness comparison beside them.

These exist for the same reason `test_audit.py` does: the numbers are the
whole product of the module, and they must be pinnable exactly. The employee
reading their hours and the manager reading the same roster are looking at
one calculation (D14) -- the test that proves it is
`test_personal_hours_match_the_managers_audit_arithmetic`.

The on-call weighting is given its own tests because it is the number that
looks like a bug when it is right: an eight-hour on-call counting as four is
`hour_weight` doing its job (D9), not arithmetic going wrong.
"""

from app.bl.audit import audit, fairness, personal_summary

# This workplace's own vocabulary, never known in advance (D9).
MORNING = "בוקר"
EVENING = "צהריים"
ON_CALL = "כונן לילה"

SHIFTS = [
    {"name": MORNING, "start_time": "07:00", "end_time": "15:00",
     "is_on_call": False, "hour_weight": 1.0},
    {"name": EVENING, "start_time": "15:00", "end_time": "23:00",
     "is_on_call": False, "hour_weight": 1.0},
    # Available rather than working: the interview collected the weight, and
    # the audit is what applies it.
    {"name": ON_CALL, "start_time": "23:00", "end_time": "07:00",
     "is_on_call": True, "hour_weight": 0.5},
]

DANA = "דנה"
YOSSI = "יוסי"
RON = "רון"


def _assignment(employee, shift, date):
    return {"employee": employee, "shift": shift, "date": date}


# --- the personal totals ----------------------------------------------------

def test_hours_count_only_the_persons_own_shifts():
    rows = [
        _assignment(DANA, MORNING, "2026-03-02"),
        _assignment(DANA, MORNING, "2026-03-03"),
        _assignment(YOSSI, MORNING, "2026-03-04"),
    ]

    summary = personal_summary(DANA, rows, SHIFTS)

    assert summary["shift_count"] == 2
    assert summary["total_hours"] == 16.0
    assert summary["days_worked"] == 2


def test_on_call_hours_are_weighted_and_reported_separately():
    """An 8-hour on-call at weight 0.5 counts as 4 -- and says so.

    The split is the point: a bare total of 12 for one morning plus one
    on-call looks wrong to the person who worked both, and the breakdown is
    what makes it legible rather than disputable.
    """
    rows = [
        _assignment(DANA, MORNING, "2026-03-02"),
        _assignment(DANA, ON_CALL, "2026-03-03"),
    ]

    summary = personal_summary(DANA, rows, SHIFTS)

    assert summary["on_call_count"] == 1
    assert summary["on_call_hours"] == 4.0
    assert summary["worked_hours"] == 8.0
    assert summary["total_hours"] == 12.0


def test_a_person_with_no_shifts_gets_zeros_rather_than_an_error():
    """The empty case is a real one -- someone genuinely unscheduled this
    period -- and it must render, not raise."""
    summary = personal_summary(RON, [_assignment(DANA, MORNING, "2026-03-02")], SHIFTS)

    assert summary["total_hours"] == 0.0
    assert summary["shift_count"] == 0
    assert summary["shifts"] == []


def test_shifts_are_grouped_by_name_with_counts():
    rows = [
        _assignment(DANA, MORNING, "2026-03-02"),
        _assignment(DANA, MORNING, "2026-03-03"),
        _assignment(DANA, EVENING, "2026-03-04"),
    ]

    by_shift = {row["shift"]: row for row in personal_summary(DANA, rows, SHIFTS)["by_shift"]}

    assert by_shift[MORNING]["count"] == 2
    assert by_shift[MORNING]["hours"] == 16.0
    assert by_shift[EVENING]["count"] == 1


def test_hours_are_grouped_by_iso_week():
    """ISO weeks, matching `_over_hours`. A person's week does not restart
    because the manager's planning period did."""
    rows = [
        _assignment(DANA, MORNING, "2026-03-02"),   # week 10
        _assignment(DANA, MORNING, "2026-03-09"),   # week 11
    ]

    weeks = personal_summary(DANA, rows, SHIFTS)["by_week"]

    assert [row["week"] for row in weeks] == ["2026-W10", "2026-W11"]
    assert all(row["hours"] == 8.0 for row in weeks)


# --- what the personal view must NOT leak -----------------------------------

def test_only_warnings_naming_this_person_are_included():
    """A colleague's warning is a colleague's business.

    The personal area is the one screen where another person's name appearing
    would be read as being about them.
    """
    warnings = [
        {"code": "over_hours", "employee": DANA, "message": "..."},
        {"code": "over_hours", "employee": YOSSI, "message": "..."},
    ]

    summary = personal_summary(DANA, [], SHIFTS, warnings=warnings)

    assert [row["employee"] for row in summary["warnings"]] == [DANA]


def test_team_wide_warnings_are_not_shown_in_a_personal_view():
    """`unfilled` and `overstaffed` carry no employee. They are the manager's
    problem, and surfacing them here invites someone to read them as theirs."""
    warnings = [{"code": "unfilled", "message": "...", "employee": ""}]

    assert personal_summary(DANA, [], SHIFTS, warnings=warnings)["warnings"] == []


def test_only_this_persons_constraints_are_included():
    """Stated reasons are personal -- "medical appointment" must not travel
    into a colleague's view."""
    availability = [
        {"employee": DANA, "reason": "בדיקה רפואית"},
        {"employee": YOSSI, "reason": "חתונה"},
    ]

    summary = personal_summary(DANA, [], SHIFTS, availability=availability)

    assert [row["employee"] for row in summary["constraints"]] == [DANA]


# --- the invariant that matters ---------------------------------------------

def test_personal_hours_match_the_managers_audit_arithmetic():
    """The employee's total is the manager's total, by construction.

    This is the reason `personal_summary` lives in `audit.py` rather than in
    `bl/`. If it is ever reimplemented elsewhere, the two will drift, and an
    employee reading 38 where their manager reads 41 is worse than showing
    nothing at all. A failure here means that drift has begun.
    """
    rows = [
        _assignment(DANA, MORNING, "2026-03-02"),
        _assignment(DANA, MORNING, "2026-03-03"),
        _assignment(DANA, MORNING, "2026-03-04"),
        _assignment(DANA, MORNING, "2026-03-05"),
        _assignment(DANA, MORNING, "2026-03-06"),
        _assignment(DANA, ON_CALL, "2026-03-07"),
    ]
    # A ceiling low enough that the audit must complain, so its own hours
    # figure is exposed in the warning details and can be compared.
    profile = {"audit_policy": {"max_weekly_hours": 10.0}}

    warnings = audit(rows, SHIFTS, [{"name": DANA}], profile=profile)
    over = [row for row in warnings if row["code"] == "over_hours"]
    summary = personal_summary(DANA, rows, SHIFTS)

    assert over, "expected the audit to report the ceiling being passed"
    assert over[0]["details"]["hours"] == summary["total_hours"]


# --- fairness ---------------------------------------------------------------

def test_fairness_reports_each_persons_delta_from_the_average():
    rows = [
        _assignment(DANA, MORNING, "2026-03-02"),
        _assignment(DANA, MORNING, "2026-03-03"),
        _assignment(YOSSI, MORNING, "2026-03-04"),
    ]
    employees = [{"name": DANA}, {"name": YOSSI}]

    result = fairness(rows, SHIFTS, employees)
    people = {row["employee"]: row for row in result["people"]}

    assert result["average_hours"] == 12.0
    assert people[DANA]["hours"] == 16.0
    assert people[DANA]["delta"] == 4.0
    assert people[YOSSI]["delta"] == -4.0


def test_someone_with_no_shifts_still_appears_in_the_fairness_list():
    """Dropping them would hide the single most significant case the
    comparison exists to reveal."""
    rows = [_assignment(DANA, MORNING, "2026-03-02")]
    employees = [{"name": DANA}, {"name": RON}]

    people = {row["employee"]: row for row in fairness(rows, SHIFTS, employees)["people"]}

    assert RON in people
    assert people[RON]["hours"] == 0.0


# --- still advisory ---------------------------------------------------------

def test_neither_function_raises_on_a_broken_roster():
    """Same contract as the rest of the module: it reports, it never blocks
    (D3). Malformed rows degrade to zeros rather than taking down the screen
    an employee is looking at."""
    junk = [None, {}, {"employee": DANA}, {"shift": MORNING, "date": "x"}]

    summary = personal_summary(DANA, junk, SHIFTS)
    result = fairness(junk, SHIFTS, [{"name": DANA}])

    assert summary["total_hours"] == 0.0
    assert result["average_hours"] == 0.0
