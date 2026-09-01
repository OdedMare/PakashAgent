"""The advisory checker: arithmetic over a roster, no model.

Table-driven per BUILD_ORDER step 3. Everything downstream trusts these
numbers, and the whole reason the audit is Python rather than a prompt is
that its answers can be pinned exactly -- so each check gets a fixture where
the expected warning is obvious by inspection.

The last test in the file is the one that matters most: the audit never
blocks. If it ever grows a raise or a veto, that test fails and D3 has been
reversed.
"""

import pytest

from app.bl.audit import (
    CONSECUTIVE,
    load_history,
    DOUBLE_BOOKED,
    MISSING_COMMANDER,
    MISSING_ROLE,
    OVERSTAFFED,
    OVER_HOURS,
    SEVERITY_NOTICE,
    SEVERITY_WARNING,
    SHORT_REST,
    UNAVAILABLE,
    UNFILLED,
    audit,
)

# A workplace vocabulary, as the interview would have collected it. Shift
# names are this workplace's own -- the audit never knows them in advance.
MORNING = "בוקר"
EVENING = "צהריים"
ON_CALL = "כונן לילה"

SHIFTS = [
    {
        "name": MORNING, "start_time": "07:00", "end_time": "15:00",
        "is_on_call": False, "hour_weight": 1.0,
        "staffing": [{"days": [], "headcount": 2, "required_roles": []}],
    },
    {
        "name": EVENING, "start_time": "15:00", "end_time": "23:00",
        "is_on_call": False, "hour_weight": 1.0,
        "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
    },
    {
        # On-call: eight clock hours that count as four, which is exactly the
        # weighting D9 says to read from the interview rather than assume.
        "name": ON_CALL, "start_time": "23:00", "end_time": "07:00",
        "is_on_call": True, "hour_weight": 0.5,
        "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
    },
]

EMPLOYEES = [
    {"name": "דנה"}, {"name": "יוסי"}, {"name": "רון"},
]


def _assign(employee, shift, date):
    return {"employee": employee, "shift": shift, "date": date}


def _codes(warnings):
    return [warning["code"] for warning in warnings]


def _by_code(warnings, code):
    return [warning for warning in warnings if warning["code"] == code]


def test_clean_schedule_produces_no_warnings():
    """A fully staffed day inside every limit warns about nothing."""
    warnings = audit(
        [
            _assign("דנה", MORNING, "2026-08-17"),
            _assign("יוסי", MORNING, "2026-08-17"),
            _assign("רון", EVENING, "2026-08-17"),
        ],
        SHIFTS, EMPLOYEES,
    )
    assert warnings == []


def test_double_booking_is_caught():
    """The same person twice on one slot."""
    warnings = audit(
        [
            _assign("דנה", MORNING, "2026-08-17"),
            _assign("דנה", MORNING, "2026-08-17"),
            _assign("רון", EVENING, "2026-08-17"),
        ],
        SHIFTS, EMPLOYEES,
    )
    doubled = _by_code(warnings, DOUBLE_BOOKED)
    assert len(doubled) == 1
    assert doubled[0]["employee"] == "דנה"
    assert doubled[0]["severity"] == SEVERITY_WARNING


def test_assignment_against_a_recorded_constraint_is_caught():
    warnings = audit(
        [_assign("דנה", MORNING, "2026-08-17")],
        SHIFTS, EMPLOYEES,
        availability=[{
            "employee": "דנה", "date": "2026-08-17", "shift": MORNING,
            "available": False, "reason": "תואר",
        }],
    )
    conflicts = _by_code(warnings, UNAVAILABLE)
    assert len(conflicts) == 1
    assert "תואר" in conflicts[0]["message"]


def test_a_whole_day_constraint_blocks_every_shift_that_day():
    """A constraint row with no shift name rules out the entire day.

    This is the question the interview asks explicitly, so the audit has to
    honour the answer rather than only matching shift-for-shift.
    """
    warnings = audit(
        [
            _assign("דנה", MORNING, "2026-08-17"),
            _assign("דנה", EVENING, "2026-08-17"),
        ],
        SHIFTS, EMPLOYEES,
        availability=[{
            "employee": "דנה", "date": "2026-08-17", "shift": "",
            "available": False, "reason": "מילואים",
        }],
    )
    assert len(_by_code(warnings, UNAVAILABLE)) == 2


def test_availability_marked_available_is_not_a_conflict():
    warnings = audit(
        [_assign("דנה", MORNING, "2026-08-17")],
        SHIFTS, EMPLOYEES,
        availability=[{
            "employee": "דנה", "date": "2026-08-17", "shift": MORNING,
            "available": True,
        }],
    )
    assert _by_code(warnings, UNAVAILABLE) == []


def test_available_from_a_time_rejects_an_earlier_shift():
    warnings = audit(
        [_assign("דנה", MORNING, "2026-08-17")],
        SHIFTS, EMPLOYEES,
        availability=[{
            "employee": "דנה", "date": "2026-08-17", "shift": "",
            "available": True, "start_time": "16:00", "is_hard": True,
        }],
    )
    conflict = _by_code(warnings, UNAVAILABLE)[0]
    assert conflict["severity"] == SEVERITY_WARNING
    assert conflict["details"]["start_time"] == "16:00"


def test_a_soft_time_window_is_a_notice_not_a_hard_warning():
    warnings = audit(
        [_assign("דנה", MORNING, "2026-08-17")],
        SHIFTS, EMPLOYEES,
        availability=[{
            "employee": "דנה", "date": "2026-08-17", "shift": "",
            "available": True, "start_time": "16:00", "is_hard": False,
            "reason": "העדפה אישית",
        }],
    )
    conflict = _by_code(warnings, UNAVAILABLE)[0]
    assert conflict["severity"] == SEVERITY_NOTICE
    assert "העדפה" in conflict["message"]


def test_weekly_hours_over_the_ceiling_are_reported():
    """Six morning shifts is 48 hours, past the 45-hour default."""
    assignments = [
        _assign("דנה", MORNING, "2026-08-%02d" % day)
        for day in range(17, 23)
    ]
    warnings = audit(assignments, SHIFTS, EMPLOYEES)
    over = _by_code(warnings, OVER_HOURS)
    assert len(over) == 1
    assert over[0]["details"]["hours"] == pytest.approx(48.0)


def test_a_personal_hour_limit_overrides_the_default():
    """`max_weekly_hours` on the employee wins over the policy default."""
    assignments = [
        _assign("דנה", MORNING, "2026-08-%02d" % day)
        for day in range(17, 20)
    ]
    warnings = audit(
        assignments, SHIFTS,
        [{"name": "דנה", "max_weekly_hours": 16}],
    )
    over = _by_code(warnings, OVER_HOURS)
    assert len(over) == 1
    assert over[0]["details"]["limit"] == pytest.approx(16.0)


def test_on_call_hours_are_weighted_not_counted_whole():
    """Eight on-call hours at weight 0.5 count as four.

    The point of D9's on-call question: counting a `כונן לילה` as a full
    night would push people over a ceiling they never actually crossed.
    """
    assignments = [
        _assign("דנה", ON_CALL, "2026-08-%02d" % day)
        for day in range(17, 23)
    ]
    warnings = audit(assignments, SHIFTS, EMPLOYEES)
    # 6 * 8 clock hours = 48 raw, but 6 * 4 weighted = 24, under the ceiling.
    assert _by_code(warnings, OVER_HOURS) == []


def test_seven_consecutive_days_is_reported():
    assignments = [
        _assign("יוסי", EVENING, "2026-08-%02d" % day)
        for day in range(17, 24)
    ]
    warnings = audit(assignments, SHIFTS, EMPLOYEES)
    runs = _by_code(warnings, CONSECUTIVE)
    assert len(runs) == 1
    assert runs[0]["details"]["days"] == 7


def test_a_break_in_the_run_resets_the_count():
    """Two runs of four with a day off between them warn about neither."""
    days = list(range(17, 21)) + list(range(22, 26))
    assignments = [
        _assign("יוסי", EVENING, "2026-08-%02d" % day) for day in days
    ]
    warnings = audit(assignments, SHIFTS, EMPLOYEES)
    assert _by_code(warnings, CONSECUTIVE) == []


def test_insufficient_rest_between_shifts_is_reported():
    """Evening ending 23:00 then morning starting 07:00 is 8 hours.

    Set against a 10-hour minimum so the fixture is unambiguous.
    """
    warnings = audit(
        [
            _assign("רון", EVENING, "2026-08-17"),
            _assign("רון", MORNING, "2026-08-18"),
        ],
        SHIFTS, EMPLOYEES,
        profile={"audit_policy": {"min_rest_hours": 10}},
    )
    rest = _by_code(warnings, SHORT_REST)
    assert len(rest) == 1
    assert rest[0]["details"]["rest_hours"] == pytest.approx(8.0)


def test_a_shift_crossing_midnight_is_measured_into_the_next_day():
    """On-call runs 23:00->07:00, so a 07:00 morning after it is zero rest."""
    warnings = audit(
        [
            _assign("רון", ON_CALL, "2026-08-17"),
            _assign("רון", MORNING, "2026-08-18"),
        ],
        SHIFTS, EMPLOYEES,
    )
    rest = _by_code(warnings, SHORT_REST)
    assert len(rest) == 1
    assert rest[0]["details"]["rest_hours"] == pytest.approx(0.0)


# -- full-time service --------------------------------------------------------
#
# A unit that closes is not a job measured in weekly hours: the three civilian
# ceilings above stop describing it, and reporting them would report the
# rotation itself as a violation every single week (D25). The unit is read off
# the rotation the interview already collected, never asked for separately.

FULL_TIME_PROFILE = {
    "workplace": {
        "name": "פלוגה", "rotation_mode": "round",
        "first_closure_date": "2026-08-29", "first_closure_group": "א",
    },
    "employees": [
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "יוסי", "exit_pattern": "round", "rotation_group": "ב"},
        {"name": "רון", "exit_pattern": "round", "rotation_group": "ב"},
    ],
}


def test_a_full_time_unit_has_no_weekly_hour_ceiling():
    """The same 48 hours that warn in a civilian roster say nothing here."""
    assignments = [
        _assign("דנה", MORNING, "2026-08-%02d" % day)
        for day in range(17, 23)
    ]
    warnings = audit(
        assignments, SHIFTS, FULL_TIME_PROFILE["employees"],
        profile=FULL_TIME_PROFILE,
    )
    assert _by_code(warnings, OVER_HOURS) == []


def test_a_full_time_unit_does_not_count_consecutive_days():
    """A closure is consecutive days by design, not by accident."""
    assignments = [
        _assign("יוסי", EVENING, "2026-08-%02d" % day)
        for day in range(17, 24)
    ]
    warnings = audit(
        assignments, SHIFTS, FULL_TIME_PROFILE["employees"],
        profile=FULL_TIME_PROFILE,
    )
    assert _by_code(warnings, CONSECUTIVE) == []


def test_a_full_time_unit_drops_the_rest_minimum():
    """Eight hours between two shifts is a closure, not a finding."""
    warnings = audit(
        [
            _assign("רון", EVENING, "2026-08-17"),
            _assign("רון", MORNING, "2026-08-18"),
        ],
        SHIFTS, FULL_TIME_PROFILE["employees"],
        profile=dict(FULL_TIME_PROFILE, audit_policy={"min_rest_hours": 10}),
    )
    assert _by_code(warnings, SHORT_REST) == []


def test_overlapping_shifts_are_still_impossible_in_a_full_time_unit():
    """The rest minimum falls to zero; it is not switched off.

    Nobody can stand two shifts at once, and a unit being full-time does not
    make them able to. A negative gap is reported as the overlap it is
    rather than as a short rest, because no amount of rest would fix it.
    """
    # A patrol that starts while the morning is still running. Declared
    # here rather than in SHIFTS because an overlap is exactly what a real
    # vocabulary avoids -- it has to be built to be tested.
    patrol = {
        "name": "סיור", "start_time": "12:00", "end_time": "20:00",
        "is_on_call": False, "hour_weight": 1.0,
        "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
    }
    warnings = audit(
        [
            _assign("רון", MORNING, "2026-08-17"),
            _assign("רון", "סיור", "2026-08-17"),
        ],
        SHIFTS + [patrol], FULL_TIME_PROFILE["employees"],
        profile=FULL_TIME_PROFILE,
    )
    rest = _by_code(warnings, SHORT_REST)
    assert len(rest) == 1
    assert rest[0]["details"]["overlapping"] is True
    assert "חופפות" in rest[0]["message"]


def test_a_civilian_roster_keeps_every_ceiling():
    """The suspension is the rotation's, not everybody's.

    Without a cycle anywhere in the profile this is an ordinary workplace and
    the three checks mean exactly what they meant before.
    """
    assignments = [
        _assign("דנה", MORNING, "2026-08-%02d" % day)
        for day in range(17, 24)
    ]
    warnings = audit(
        assignments, SHIFTS, EMPLOYEES,
        profile={"workplace": {"name": "מוקד"}, "employees": EMPLOYEES},
    )
    assert len(_by_code(warnings, OVER_HOURS)) == 1
    assert len(_by_code(warnings, CONSECUTIVE)) == 1


def test_a_cleared_hour_ceiling_means_no_ceiling_not_a_ceiling_of_zero():
    """A manager who empties the field is saying hours are not the measure."""
    assignments = [
        _assign("דנה", MORNING, "2026-08-%02d" % day)
        for day in range(17, 23)
    ]
    warnings = audit(
        assignments, SHIFTS, EMPLOYEES,
        profile={"audit_policy": {"max_weekly_hours": 0}},
    )
    assert _by_code(warnings, OVER_HOURS) == []


def test_an_understaffed_slot_is_reported():
    """Morning needs two; one is assigned."""
    warnings = audit(
        [_assign("דנה", MORNING, "2026-08-17")], SHIFTS, EMPLOYEES,
    )
    unfilled = _by_code(warnings, UNFILLED)
    assert len(unfilled) == 1
    assert unfilled[0]["details"] == {"assigned": 1, "required": 2}


def test_required_role_is_checked_from_the_shift_staffing_contract():
    shifts = [dict(SHIFTS[1], staffing=[{
        "days": [], "headcount": 1, "required_roles": ["אחראית"],
    }])]
    warnings = audit(
        [_assign("יוסי", EVENING, "2026-08-17")],
        shifts,
        [{"name": "יוסי", "role": "נציג"}],
    )

    missing = _by_code(warnings, MISSING_ROLE)
    assert len(missing) == 1
    assert missing[0]["details"] == {"required_role": "אחראית"}


def test_shift_requiring_a_commander_checks_the_employee_capability():
    shifts = [dict(SHIFTS[1], requires_shift_manager=True)]
    slots = [{
        "shift_name": EVENING, "slot_date": "2026-08-17",
        "requires_shift_manager": True,
    }]
    assignments = [_assign("יוסי", EVENING, "2026-08-17")]

    missing = audit(assignments, shifts, [{"name": "יוסי"}], slots=slots)
    assert len(_by_code(missing, MISSING_COMMANDER)) == 1

    staffed = audit(
        assignments, shifts,
        [{"name": "יוסי", "is_shift_manager": True}], slots=slots,
    )
    assert _by_code(staffed, MISSING_COMMANDER) == []


def test_non_counting_trainee_does_not_fill_or_overstaff_a_slot():
    shifts = [dict(SHIFTS[1], staffing=[{
        "days": [], "headcount": 1, "required_roles": [],
    }])]
    employees = [{
        "name": "מתלמד", "is_trainee": True,
        "counts_toward_staffing": False,
    }]

    warnings = audit(
        [_assign("מתלמד", EVENING, "2026-08-17")],
        shifts, employees,
    )

    assert len(_by_code(warnings, UNFILLED)) == 1
    assert _by_code(warnings, OVERSTAFFED) == []


def test_an_overstaffed_slot_is_a_notice_not_a_warning():
    """Costs money, breaks nothing -- and may well be deliberate."""
    warnings = audit(
        [
            _assign("דנה", EVENING, "2026-08-17"),
            _assign("יוסי", EVENING, "2026-08-17"),
        ],
        SHIFTS, EMPLOYEES,
    )
    over = _by_code(warnings, OVERSTAFFED)
    assert len(over) == 1
    assert over[0]["severity"] == SEVERITY_NOTICE


def test_per_day_staffing_overrides_the_default_group():
    """A group naming this weekday beats the group naming none.

    2026-08-21 is a Friday; the fixture asks for one person on Fridays and
    two the rest of the week.
    """
    shifts = [{
        "name": MORNING, "start_time": "07:00", "end_time": "15:00",
        "is_on_call": False, "hour_weight": 1.0,
        "staffing": [
            {"days": [], "headcount": 2, "required_roles": []},
            {"days": ["יום שישי"], "headcount": 1, "required_roles": []},
        ],
    }]
    warnings = audit(
        [_assign("דנה", MORNING, "2026-08-21")], shifts, EMPLOYEES,
    )
    assert _by_code(warnings, UNFILLED) == []


def test_an_unknown_shift_name_contributes_no_invented_hours():
    """A shift the vocabulary does not have still counts as a slot filled,
    but contributes zero hours rather than a guessed length."""
    assignments = [
        {"employee": "דנה", "shift": "משמרת שלא קיימת",
         "date": "2026-08-%02d" % day}
        for day in range(17, 24)
    ]
    warnings = audit(assignments, SHIFTS, EMPLOYEES)
    assert _by_code(warnings, OVER_HOURS) == []
    # It is still seven consecutive days of work.
    assert len(_by_code(warnings, CONSECUTIVE)) == 1


def test_malformed_rows_are_skipped_rather_than_raising():
    """The audit is handed model-produced data and must never be the thing
    that takes a schedule down."""
    warnings = audit(
        [
            None,
            "not a row",
            {"employee": "", "shift": MORNING, "date": "2026-08-17"},
            {"employee": "דנה", "shift": MORNING, "date": "not-a-date"},
            _assign("דנה", MORNING, "2026-08-17"),
        ],
        SHIFTS, EMPLOYEES,
    )
    assert isinstance(warnings, list)


def test_empty_inputs_are_not_an_error():
    assert audit([], [], []) == []
    assert audit(None, None, None) == []


def test_warnings_sort_stably_with_warnings_before_notices():
    """The manager reads this list top-down; two identical audits must not
    reorder themselves."""
    assignments = [
        _assign("דנה", MORNING, "2026-08-17"),
        _assign("יוסי", EVENING, "2026-08-17"),
        _assign("רון", EVENING, "2026-08-17"),
    ]
    first = audit(assignments, SHIFTS, EMPLOYEES)
    second = audit(list(reversed(assignments)), SHIFTS, EMPLOYEES)
    assert _codes(first) == _codes(second)
    severities = [warning["severity"] for warning in first]
    assert severities == sorted(
        severities, key=lambda value: 0 if value == SEVERITY_WARNING else 1
    )


def test_the_audit_never_blocks_and_never_mutates():
    """D3, asserted directly.

    The audit reports. It does not raise on a broken rule, does not return
    a rejection the caller must honour, and does not touch what it was
    handed. A schedule that breaks every rule in the file still comes back
    as a list of warnings and an untouched schedule.
    """
    assignments = [
        _assign("דנה", MORNING, "2026-08-%02d" % day)
        for day in range(17, 25)
    ] + [_assign("דנה", MORNING, "2026-08-17")]
    before = [dict(row) for row in assignments]
    availability = [{
        "employee": "דנה", "date": "2026-08-17", "shift": "",
        "available": False,
    }]

    warnings = audit(assignments, SHIFTS, EMPLOYEES, availability=availability)

    # Every category fired...
    assert {OVER_HOURS, CONSECUTIVE, DOUBLE_BOOKED, UNAVAILABLE} <= set(
        _codes(warnings)
    )
    # ...and nothing was rejected, rewritten, or removed.
    assert assignments == before
    assert all(isinstance(warning, dict) for warning in warnings)


# -- the slot grid ---------------------------------------------------------

def test_a_slot_with_nobody_on_it_is_reported_when_the_grid_is_given():
    """An entirely unstaffed shift leaves no row among the assignments.

    Walking only the assignments would skip it silently -- and a shift with
    nobody on it is the single case the manager most needs told about, since
    the failure mode is that no one turns up. The schedule's own grid is what
    makes it visible.
    """
    slots = [
        {"shift_name": MORNING, "slot_date": "2026-08-17"},
        {"shift_name": MORNING, "slot_date": "2026-08-18"},
    ]
    warnings = audit(
        [_assign("דנה", MORNING, "2026-08-17"), _assign("יוסי", MORNING, "2026-08-17")],
        SHIFTS, EMPLOYEES, slots=slots,
    )
    unfilled = _by_code(warnings, UNFILLED)
    assert len(unfilled) == 1
    assert unfilled[0]["date"] == "2026-08-18"
    assert unfilled[0]["details"] == {"assigned": 0, "required": 2}


def test_slot_dates_may_arrive_as_dates_rather_than_strings():
    """Repository rows carry `datetime.date`; a grid built in memory carries
    strings. Both have to compare against the assignment dates."""
    import datetime

    slots = [{
        "shift_name": MORNING,
        "slot_date": datetime.date(2026, 8, 18),
    }]
    warnings = audit([], SHIFTS, EMPLOYEES, slots=slots)
    assert len(_by_code(warnings, UNFILLED)) == 1


def test_without_a_grid_the_audit_still_checks_what_it_can_see():
    """The assignments remain the fallback, so an older caller keeps working."""
    warnings = audit(
        [_assign("דנה", MORNING, "2026-08-17")], SHIFTS, EMPLOYEES,
    )
    assert len(_by_code(warnings, UNFILLED)) == 1


# --- load_history: the fairness tally the scheduler reasons from -----------

_LOAD_SHIFTS = [
    {"name": "בוקר", "start_time": "07:00", "end_time": "15:00"},
    {"name": "לילה", "start_time": "23:00", "end_time": "07:00",
     "is_night": True},
    {"name": "כונן לילה", "start_time": "23:00", "end_time": "07:00",
     "is_on_call": True},
]
_LOAD_EMPLOYEES = [{"name": "רון"}, {"name": "דנה"}, {"name": "יוסי"}]


def _load(assignments):
    rows = load_history(assignments, _LOAD_SHIFTS, _LOAD_EMPLOYEES)
    return {row["employee"]: row for row in rows}


def test_load_history_keeps_everyone_including_people_with_no_shifts():
    """A zero is the most useful row in the table — it is who the next night
    should go to. An absent row reads as missing data instead."""
    by_name = _load([{"employee": "רון", "shift": "בוקר", "date": "2026-08-03"}])
    assert set(by_name) == {"רון", "דנה", "יוסי"}
    assert by_name["יוסי"]["shifts"] == 0
    assert by_name["יוסי"]["nights"] == 0
    assert by_name["יוסי"]["last_worked"] == ""


def test_load_history_counts_nights_from_the_shift_flag():
    by_name = _load([
        {"employee": "רון", "shift": "לילה", "date": "2026-08-03"},
        {"employee": "רון", "shift": "בוקר", "date": "2026-08-04"},
    ])
    assert by_name["רון"]["shifts"] == 2
    assert by_name["רון"]["nights"] == 1


def test_on_call_counts_as_a_night():
    """`כונן לילה` is a night the person carries, whatever it weighs toward
    hours (D9)."""
    by_name = _load([
        {"employee": "דנה", "shift": "כונן לילה", "date": "2026-08-03"},
    ])
    assert by_name["דנה"]["nights"] == 1


def test_a_shift_the_vocabulary_does_not_mark_is_not_guessed_into_a_night():
    """Never inferred from the name or the start time — the vocabulary is
    per-workplace, and guessing is the hardcoding D9 forbids."""
    by_name = _load([
        {"employee": "רון", "shift": "בוקר", "date": "2026-08-03"},
    ])
    assert by_name["רון"]["nights"] == 0


def test_load_history_counts_weekends():
    """2026-08-07 is a Friday and 08-08 a Saturday."""
    by_name = _load([
        {"employee": "רון", "shift": "בוקר", "date": "2026-08-07"},
        {"employee": "רון", "shift": "בוקר", "date": "2026-08-08"},
        {"employee": "רון", "shift": "בוקר", "date": "2026-08-10"},
    ])
    assert by_name["רון"]["weekends"] == 2
    assert by_name["רון"]["shifts"] == 3


def test_load_history_tracks_the_most_recent_date():
    by_name = _load([
        {"employee": "רון", "shift": "בוקר", "date": "2026-08-03"},
        {"employee": "רון", "shift": "בוקר", "date": "2026-08-11"},
        {"employee": "רון", "shift": "בוקר", "date": "2026-08-07"},
    ])
    assert by_name["רון"]["last_worked"] == "2026-08-11"


def test_a_name_no_longer_on_the_roster_is_still_counted():
    """Dropping them would understate how much of the load the people still
    here actually carried."""
    by_name = _load([
        {"employee": "מי שעזב", "shift": "לילה", "date": "2026-08-03"},
    ])
    assert by_name["מי שעזב"]["nights"] == 1


def test_load_history_is_ordered_by_who_carried_the_most():
    rows = load_history([
        {"employee": "דנה", "shift": "לילה", "date": "2026-08-03"},
        {"employee": "דנה", "shift": "לילה", "date": "2026-08-04"},
        {"employee": "רון", "shift": "לילה", "date": "2026-08-05"},
    ], _LOAD_SHIFTS, _LOAD_EMPLOYEES)
    assert [row["employee"] for row in rows] == ["דנה", "רון", "יוסי"]


def test_load_history_survives_junk_rows():
    rows = load_history(
        [None, "not a dict", {}, {"employee": "רון"}],
        _LOAD_SHIFTS, _LOAD_EMPLOYEES,
    )
    assert {row["employee"] for row in rows} == {"רון", "דנה", "יוסי"}
    assert all(row["shifts"] == 0 for row in rows)
