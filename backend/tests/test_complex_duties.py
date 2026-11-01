"""A מכלול duty holds the soldier for the whole day.

The duty is stored by the מכלול (`complex_duties`) and projected into each
team's availability as a `duty` with no hours. These pin down what "the
whole day" means -- midnight to midnight, so a night shift reaching into
it is blocked from either side -- and that the solver, the write guard and
the scheduling window all read it that way.
"""

import pytest

from app.bl.audit import constraint_conflicts, is_whole_day
from app.bl.scheduler.availability import effective_availability
from app.bl.solver import generate_span

DAY = "2026-11-10"
BEFORE = "2026-11-09"
AFTER = "2026-11-11"


def _duty(employee="דנה", date=DAY):
    return {
        "employee": employee, "constraint_date": date, "shift_name": "",
        "available": False, "start_time": "", "end_time": "", "is_hard": True,
        "reason": "מטבח", "source": "complex", "constraint_type": "duty",
    }


def _shift(date, start, end, employee="דנה"):
    return {"employee": employee, "date": date, "shift": "x",
            "start_time": start, "end_time": end}


@pytest.mark.parametrize("assignment, blocked", [
    (_shift(DAY, "07:00", "15:00"), True),            # that day's morning
    (_shift(DAY, "23:00", "07:00"), True),            # that night, starting on it
    (_shift(BEFORE, "23:00", "07:00"), True),         # last night, ending on it
    (_shift(BEFORE, "15:00", "23:00"), False),        # the evening before
    (_shift(BEFORE, "16:00", "00:00"), False),        # ends exactly at midnight
    (_shift(AFTER, "07:00", "15:00"), False),         # the next morning
    (_shift(DAY, "", ""), True),                      # no hours, same date
    (_shift(BEFORE, "", ""), False),                  # no hours, other date
    (_shift(DAY, "07:00", "15:00", employee="יוסי"), False),
])
def test_a_whole_day_duty_blocks_every_shift_touching_its_day(assignment, blocked):
    assert constraint_conflicts(assignment, _duty()) is blocked


def test_only_a_duty_without_hours_is_whole_day():
    assert is_whole_day(_duty())
    assert not is_whole_day(dict(_duty(), start_time="22:00", end_time="06:00"))


def test_a_duty_the_day_after_the_span_still_reaches_its_last_night():
    rows = [_duty(date=AFTER), _duty(date=BEFORE), _duty(date="2026-11-12")]

    kept = effective_availability({}, rows, DAY, DAY)

    assert sorted(row["date"] for row in kept) == [BEFORE, AFTER]


def _profile(*names):
    return {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": name, "eligible_shifts": ["בוקר", "לילה"]} for name in names],
        "shifts": [
            {"name": "בוקר", "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
            {"name": "לילה", "start_time": "23:00", "end_time": "07:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
        ],
        "audit_policy": {"min_rest_hours": 0},
    }


def test_the_solver_places_nobody_on_duty_that_day_or_the_night_before():
    duty = dict(_duty(), date=DAY)

    result = generate_span(_profile("דנה", "יוסי", "רון"), BEFORE, DAY,
                           availability=[duty])

    placed = [(row["date"], row["shift"]) for row in result["assignments"]
              if row["employee"] == "דנה"]
    assert (DAY, "בוקר") not in placed
    assert (DAY, "לילה") not in placed
    assert (BEFORE, "לילה") not in placed


# --- fairness: a duty day is a shift already carried ------------------------

SPAN = ("2026-11-16", "2026-11-19")  # Monday to Thursday, one seat a day


def _one_seat(*names):
    return {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": name, "eligible_shifts": ["בוקר"]} for name in names],
        "shifts": [{"name": "בוקר", "start_time": "07:00", "end_time": "15:00", "days": [],
                    "staffing": [{"days": [], "headcount": 1, "required_roles": []}]}],
    }


def _carried(date, weight=1, employee="דנה"):
    """A `team_complex_duties` row, as the build hands the solver."""
    return {"employee": employee, "duty_date": date, "weight": weight}


def _counts(duties):
    result = generate_span(_one_seat("דנה", "יוסי"), *SPAN, duties=duties)
    counts = {"דנה": 0, "יוסי": 0}
    for row in result["assignments"]:
        counts[row["employee"]] += 1
    return counts


def test_without_duties_the_load_is_shared_as_before():
    assert _counts([]) == {"דנה": 2, "יוסי": 2}


def test_whoever_stood_a_duty_takes_fewer_shifts():
    # Two duty days in the week before: the target is three each, counting them.
    assert _counts([_carried("2026-11-12"), _carried("2026-11-13")]) == {"דנה": 1, "יוסי": 3}


def test_a_heavier_duty_counts_more():
    assert _counts([_carried("2026-11-13", weight=2)]) == {"דנה": 1, "יוסי": 3}


@pytest.mark.parametrize("row", [
    _carried("2026-11-13", weight=0),            # counts nothing by its type
    _carried("2026-10-20"),                      # long before the window
    _carried("2026-11-13", employee="אבי"),      # nobody on this roster
])
def test_what_carries_no_load(row):
    assert _counts([row]) == {"דנה": 2, "יוסי": 2}


def test_the_build_says_the_duties_were_counted():
    profile = _one_seat("דנה", "יוסי")
    counted = generate_span(profile, *SPAN, duties=[_carried("2026-11-13", weight=2)])
    plain = generate_span(profile, *SPAN, duties=[])

    assert "תורנויות המכלול נספרו בעומס, כל יום תורנות כמשמרת לפי משקלו: דנה (2)" in counted["notes"]
    assert not any("תורנויות המכלול" in note for note in plain["notes"])


def test_a_team_duty_in_the_availability_carries_no_load():
    """Only מכלול duties count as load; a team's own timed duty blocks."""
    own = dict(_duty(date="2026-11-13"), source="manager", start_time="08:00",
               end_time="12:00", date="2026-11-13")
    result = generate_span(_one_seat("דנה", "יוסי"), *SPAN, availability=[own])
    assert sorted(row["employee"] for row in result["assignments"]) == ["דנה", "דנה", "יוסי", "יוסי"]
