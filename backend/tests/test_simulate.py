"""What `bl/simulate.py` says a change would do, without doing it.

Pure functions over fixtures, like `test_placement.py` and `test_audit.py`.
There is no model and no repository anywhere in this file, which is the
property being tested as much as any individual case.

Three things here are the point of the feature:

- **It persists nothing**, and it *can* persist nothing — the module is handed
  no repository at all, so the input it is given is the only state it sees
  and the input is never mutated.
- **The diff is a diff.** A warning already standing is not reported as
  introduced, and one that merely gets worse is not reported as new.
- **Everybody affected is named**, including the person a change takes a
  shift *away* from.
"""

import copy

import pytest

from app.bl.simulate import simulate

MORNING = "בוקר"
EVENING = "צהריים"

DANA = "דנה"
YOSSI = "יוסי"
RON = "רון"

PROFILE = {
    "workplace": {"name": "מוקד"},
    "employees": [
        {"name": DANA, "eligible_shifts": [MORNING]},
        {"name": YOSSI, "eligible_shifts": [MORNING, EVENING]},
        {"name": RON, "eligible_shifts": [MORNING, EVENING]},
    ],
    "shifts": [
        {
            "name": MORNING, "start_time": "07:00", "end_time": "15:00",
            "days": [], "is_on_call": False, "hour_weight": 1.0,
            "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
        },
        {
            "name": EVENING, "start_time": "15:00", "end_time": "23:00",
            "days": [], "is_on_call": False, "hour_weight": 1.0,
            "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
        },
    ],
    "rules": [],
}

DATES = ("2026-08-17", "2026-08-18")


def _schedule(assignments):
    slots = [
        {
            "id": "slot-%s-%s" % (shift, date),
            "shift_name": shift, "slot_date": date,
            "start_time": "07:00" if shift == MORNING else "15:00",
            "end_time": "15:00" if shift == MORNING else "23:00",
            "headcount": 1, "is_on_call": False,
        }
        for date in DATES for shift in (MORNING, EVENING)
    ]
    rows = [
        dict(item, id="asg-%d" % index, reason="בדיקה")
        for index, item in enumerate(assignments)
    ]
    return {
        "id": "sched-1", "starts_on": DATES[0], "ends_on": DATES[1],
        "status": "draft", "slots": slots, "assignments": rows,
    }


def _assign(employee, shift, date):
    return {
        "action": "assign", "employee": employee, "shift": shift,
        "date": date, "reason": "בדיקה",
    }


def _remove(employee, shift, date):
    return {
        "action": "remove", "employee": employee, "shift": shift,
        "date": date, "reason": "בדיקה",
    }


# -- it does not persist ---------------------------------------------------


def test_the_input_schedule_is_never_mutated():
    """The strongest form of "persists nothing": it does not even touch it."""
    schedule = _schedule([
        {"employee": DANA, "shift": MORNING, "date": DATES[0]},
    ])
    before = copy.deepcopy(schedule)
    simulate(schedule, PROFILE, [_assign(YOSSI, EVENING, DATES[0])])
    assert schedule == before


def test_every_result_says_it_is_a_simulation():
    """The field the UI colours off. It is never false."""
    result = simulate(_schedule([]), PROFILE, [_assign(YOSSI, EVENING, DATES[0])])
    assert result["simulated"] is True


def test_nothing_applied_is_reported_rather_than_looking_harmless():
    result = simulate(_schedule([]), PROFILE, [])
    assert result["applied"] is False


# -- applying --------------------------------------------------------------


def test_assigning_into_an_empty_slot_improves_coverage():
    result = simulate(
        _schedule([]), PROFILE, [_assign(YOSSI, EVENING, DATES[0])],
    )
    assert result["applied"] is True
    assert result["coverage"]["delta"] == 1
    assert result["coverage"]["assigned_after"] == 1


def test_removing_somebody_costs_coverage():
    result = simulate(
        _schedule([{"employee": DANA, "shift": MORNING, "date": DATES[0]}]),
        PROFILE,
        [_remove(DANA, MORNING, DATES[0])],
    )
    assert result["coverage"]["delta"] == -1


def test_a_swap_moves_both_people():
    schedule = _schedule([
        {"employee": YOSSI, "shift": MORNING, "date": DATES[0]},
        {"employee": RON, "shift": EVENING, "date": DATES[0]},
    ])
    result = simulate(schedule, PROFILE, [{
        "action": "swap", "employee": YOSSI, "shift": MORNING,
        "date": DATES[0], "with_employee": RON, "with_shift": EVENING,
        "with_date": DATES[0], "reason": "בדיקה",
    }])
    assert result["applied"] is True
    assert set(result["affected"]) == {YOSSI, RON}
    # A swap moves people between existing slots, so coverage is unchanged.
    assert result["coverage"]["delta"] == 0


def test_an_operation_naming_a_slot_the_period_lacks_is_reported():
    """The manager asked what would happen; "that shift is not here" is it."""
    result = simulate(
        _schedule([]), PROFILE, [_assign(YOSSI, EVENING, "2027-01-01")],
    )
    assert result["applied"] is False
    assert result["skipped"]
    assert result["skipped"][0]["why"]


def test_removing_somebody_who_is_not_there_is_skipped_with_a_reason():
    result = simulate(
        _schedule([]), PROFILE, [_remove(DANA, MORNING, DATES[0])],
    )
    assert result["applied"] is False
    assert DANA in result["skipped"][0]["why"]


def test_a_removal_without_a_shift_name_takes_them_off_that_day():
    """"take דנה off Thursday" is a sentence the product accepts elsewhere."""
    result = simulate(
        _schedule([{"employee": DANA, "shift": MORNING, "date": DATES[0]}]),
        PROFILE,
        [{"action": "remove", "employee": DANA, "shift": "",
          "date": DATES[0], "reason": "בדיקה"}],
    )
    assert result["applied"] is True
    assert result["coverage"]["delta"] == -1


# -- the warning diff ------------------------------------------------------


def test_a_warning_the_change_causes_is_introduced():
    """דנה twice on one morning is a double-booking the change created."""
    schedule = _schedule([
        {"employee": DANA, "shift": MORNING, "date": DATES[0]},
    ])
    result = simulate(schedule, PROFILE, [_assign(DANA, EVENING, DATES[0])])
    assert result["introduced"]


def test_a_warning_the_change_clears_is_resolved():
    """Filling every slot clears the unfilled warnings that were standing."""
    schedule = _schedule([])
    result = simulate(schedule, PROFILE, [
        _assign(DANA, MORNING, DATES[0]),
        _assign(YOSSI, EVENING, DATES[0]),
        _assign(RON, MORNING, DATES[1]),
        _assign(YOSSI, EVENING, DATES[1]),
    ])
    assert result["resolved"]
    assert result["coverage"]["percent_after"] == 100


def test_a_standing_warning_is_not_blamed_on_the_change():
    """The board's existing state is not a consequence of this gesture."""
    schedule = _schedule([])
    # Every slot is empty, so unfilled warnings already stand. Filling one
    # of them must not report the other three as newly introduced.
    result = simulate(schedule, PROFILE, [_assign(DANA, MORNING, DATES[0])])
    assert result["introduced"] == []


def test_a_warning_that_only_worsens_is_not_reported_as_new():
    """`_over_hours` writes its running total into the message.

    Diffing on the message would make 46 → 54 hours read as a brand-new
    warning instead of the one already standing, which is why the key is
    code/person/date/shift.
    """
    rows = []
    # Seven consecutive mornings for one person: consecutive-days warnings
    # already stand before anything is simulated.
    dates = ["2026-08-%02d" % day for day in range(10, 17)]
    slots = [
        {"id": "slot-%s" % date, "shift_name": MORNING, "slot_date": date,
         "start_time": "07:00", "end_time": "15:00", "headcount": 1,
         "is_on_call": False}
        for date in dates + ["2026-08-17"]
    ]
    for index, date in enumerate(dates):
        rows.append({
            "id": "asg-%d" % index, "employee": YOSSI,
            "shift": MORNING, "date": date, "reason": "בדיקה",
        })
    schedule = {
        "id": "s", "starts_on": dates[0], "ends_on": "2026-08-17",
        "status": "draft", "slots": slots, "assignments": rows,
    }
    result = simulate(schedule, PROFILE, [_assign(YOSSI, MORNING, "2026-08-17")])
    # The run gets longer, but it is the same warning about the same person.
    introduced_codes = {row["code"] for row in result["introduced"]}
    assert "consecutive_days" not in introduced_codes


# -- who is affected -------------------------------------------------------


def test_the_person_losing_a_shift_is_affected_too():
    """Half an answer to "who does this touch" is the failure mode here."""
    schedule = _schedule([
        {"employee": DANA, "shift": MORNING, "date": DATES[0]},
    ])
    result = simulate(schedule, PROFILE, [
        _remove(DANA, MORNING, DATES[0]),
        _assign(RON, MORNING, DATES[0]),
    ])
    assert set(result["affected"]) == {DANA, RON}


def test_workload_reports_hours_before_and_after():
    schedule = _schedule([
        {"employee": DANA, "shift": MORNING, "date": DATES[0]},
    ])
    result = simulate(schedule, PROFILE, [
        _remove(DANA, MORNING, DATES[0]),
        _assign(RON, MORNING, DATES[0]),
    ])
    by_name = {row["employee"]: row for row in result["workload"]}
    assert by_name[DANA]["hours_before"] == 8.0
    assert by_name[DANA]["hours_after"] == 0.0
    assert by_name[DANA]["delta"] == -8.0
    assert by_name[RON]["delta"] == 8.0


def test_workload_lists_only_the_people_the_change_touches():
    """A table of twenty names buries the two that moved."""
    schedule = _schedule([
        {"employee": DANA, "shift": MORNING, "date": DATES[0]},
    ])
    result = simulate(schedule, PROFILE, [_assign(YOSSI, EVENING, DATES[0])])
    assert [row["employee"] for row in result["workload"]] == [YOSSI]


# -- coverage arithmetic ---------------------------------------------------


def test_overstaffing_does_not_inflate_coverage():
    """Three on a one-person shift is one covered place, not three."""
    schedule = _schedule([
        {"employee": DANA, "shift": MORNING, "date": DATES[0]},
    ])
    result = simulate(schedule, PROFILE, [
        _assign(YOSSI, MORNING, DATES[0]),
        _assign(RON, MORNING, DATES[0]),
    ])
    assert result["coverage"]["assigned_after"] == 1
    assert result["coverage"]["delta"] == 0


def test_coverage_percent_is_out_of_the_required_seats():
    schedule = _schedule([])
    result = simulate(schedule, PROFILE, [_assign(DANA, MORNING, DATES[0])])
    assert result["coverage"]["required"] == 4
    assert result["coverage"]["percent_before"] == 0
    assert result["coverage"]["percent_after"] == 25


@pytest.mark.parametrize("shift", [MORNING, EVENING])
def test_shift_names_come_from_the_profile(shift):
    """No literal shift name decides anything here (D9)."""
    result = simulate(_schedule([]), PROFILE, [_assign(YOSSI, shift, DATES[0])])
    assert result["applied"] is True
