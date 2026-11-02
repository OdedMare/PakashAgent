"""Patterns one person carries alone: none, daily, and one weekend in N."""

import datetime

import pytest

from app.bl import rotation
from app.bl.profile_service.roster import employees, validate_rotation_groups
from app.bl.solver import generate_span
from app.common.errors import AgentError

MORNING, EVENING = "בוקר", "ערב"


def _profile(people, headcount=1):
    return {
        "workplace": {"name": "יחידה", "round_first_closure_date": "2026-08-29",
                      "round_first_closure_group": "א"},
        "employees": people,
        "shifts": [
            {"name": MORNING, "start_time": "08:00", "end_time": "16:00", "days": [],
             "staffing": [{"days": [], "headcount": headcount, "required_roles": []}]},
            {"name": EVENING, "start_time": "16:00", "end_time": "23:00", "days": [],
             "staffing": [{"days": [], "headcount": headcount, "required_roles": []}]},
        ],
    }


def _worked(result, name):
    return {(row["date"], row["shift"]) for row in result["assignments"] if row["employee"] == name}


# -- one weekend in N --------------------------------------------------------

def _commander(**fields):
    return dict({"name": "מפקד", "exit_pattern": "personal", "closure_every": 5,
                 "closure_from": "2026-09-03"}, **fields)  # a Thursday: weekend of 05/09


def test_a_personal_closer_holds_only_their_own_weekends():
    people = employees([_commander(), {"name": "אחר", "exit_pattern": "none"}])
    result = generate_span(_profile(people, headcount=2), "2026-09-03", "2026-09-13")

    dates = {date for date, _ in _worked(result, "מפקד")}
    # Their weekend (Thu 03/09 – Sat 05/09) is worked; the next one (10–12/09) is home.
    assert {"2026-09-03", "2026-09-04", "2026-09-05"} <= dates
    assert not dates & {"2026-09-10", "2026-09-11", "2026-09-12"}
    # Weekdays between are ordinary days on base.
    assert "2026-09-08" in dates


def test_the_turn_comes_round_every_n_weeks():
    person = _commander()
    rows = rotation.closure_days({"shifts": []}, person,
                                 datetime.date(2026, 9, 1), datetime.date(2026, 11, 1))
    assert sorted({row["weekend"] for row in rows}) == ["2026-09-05", "2026-10-10"]


def test_a_personal_closer_without_a_start_is_a_configuration_error():
    profile = _profile(employees([_commander(closure_from="")]))
    assert any("הסגירה הראשונה" in error for error in rotation.configuration_errors(profile))


def test_personal_drops_a_group_and_needs_no_cycle():
    rows = employees([_commander(rotation_group="ב")])
    assert rows[0]["rotation_group"] == ""
    validate_rotation_groups({"workplace": {}, "employees": rows})


@pytest.mark.parametrize("count", [1, 9, "x"])
def test_personal_refuses_an_out_of_range_n(count):
    with pytest.raises(AgentError):
        employees([_commander(closure_every=count)])


# -- daily -------------------------------------------------------------------

def test_a_daily_soldier_works_only_their_days_and_hours():
    people = employees([
        {"name": "יומי", "exit_pattern": "daily", "daily_days": ["ראשון", "שני", "שלישי"],
         "daily_start": "07:00", "daily_end": "17:00"},
        {"name": "אחר", "exit_pattern": "none"},
    ])
    result = generate_span(_profile(people, headcount=2), "2026-08-30", "2026-09-05")

    worked = _worked(result, "יומי")
    assert worked == {("2026-08-30", MORNING), ("2026-08-31", MORNING), ("2026-09-01", MORNING)}


def test_daily_refuses_an_unknown_day():
    with pytest.raises(AgentError):
        employees([{"name": "יומי", "exit_pattern": "daily", "daily_days": ["Monday"]}])


# -- none --------------------------------------------------------------------

def test_none_is_never_blocked_and_owes_nothing():
    people = employees([{"name": "אזרח", "exit_pattern": "none", "rotation_group": "א"}])
    profile = _profile(people)
    assert people[0]["rotation_group"] == ""
    assert rotation.configuration_errors(profile) == []
    result = generate_span(profile, "2026-09-03", "2026-09-06")
    assert len(_worked(result, "אזרח")) >= 4
