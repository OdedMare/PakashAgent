"""A headcount of 0 means the shift does not run on those days."""

import pytest

from app.bl.profile_service.shifts import shifts as validate_shifts
from app.bl.scheduler import build_slots
from app.bl.solver import generate_span
from app.common.errors import AgentError

SHIFT = "בוקר"
# 2026-08-20 is a Thursday, 2026-08-21 a Friday, 2026-08-22 a Saturday.
THURSDAY, FRIDAY, SATURDAY = "2026-08-20", "2026-08-21", "2026-08-22"


def _shift(default, weekend):
    return {"name": SHIFT, "start_time": "07:00", "end_time": "15:00", "days": [],
            "staffing": [{"days": [], "headcount": default, "required_roles": []},
                         {"days": ["שישי", "שבת"], "headcount": weekend,
                          "required_roles": [], "closure": True}]}


def _dates(shift):
    return [slot["slot_date"] for slot in build_slots({"shifts": [shift]}, THURSDAY, SATURDAY)]


def test_zero_on_the_weekend_opens_no_weekend_slot():
    assert _dates(_shift(2, 0)) == [THURSDAY]


def test_zero_midweek_runs_the_shift_only_on_the_weekend():
    assert _dates(_shift(0, 3)) == [FRIDAY, SATURDAY]


def test_setup_keeps_a_zero_instead_of_raising_it_to_one():
    saved = validate_shifts([dict(_shift(0, 0), headcount=0)])[0]["staffing"]
    assert [group["headcount"] for group in saved] == [0, 0]
    flat = validate_shifts([{"name": SHIFT, "headcount": 0}])[0]["staffing"]
    assert flat[0]["headcount"] == 0
    assert validate_shifts([{"name": SHIFT}])[0]["staffing"][0]["headcount"] == 1


@pytest.mark.parametrize("value", [-1, 101, "many", True])
def test_setup_refuses_a_headcount_out_of_range(value):
    with pytest.raises(AgentError):
        validate_shifts([dict(_shift(1, value))])


def test_the_solver_places_nobody_on_a_day_the_shift_is_off():
    profile = {"workplace": {"name": "יחידה"}, "shifts": [_shift(1, 0)],
               "employees": [{"name": "דנה", "eligible_shifts": [SHIFT]}]}
    result = generate_span(profile, THURSDAY, SATURDAY)
    assert [row["date"] for row in result["assignments"]] == [THURSDAY]
    assert not [item for item in result["warnings"] if item.get("date") in (FRIDAY, SATURDAY)]


def test_a_temporary_shift_opens_slots_only_inside_its_date_window():
    shift = dict(_shift(1, 1), starts_on="2026-08-19", ends_on=SATURDAY)
    dates = [slot["slot_date"] for slot in build_slots(
        {"shifts": [shift]}, "2026-08-17", "2026-08-24",
    )]
    assert dates == ["2026-08-19", THURSDAY, FRIDAY, SATURDAY]


def test_a_temporary_shift_requires_a_valid_complete_date_window():
    [saved] = validate_shifts([dict(_shift(1, 1), starts_on=THURSDAY, ends_on=SATURDAY)])
    assert (saved["starts_on"], saved["ends_on"]) == (THURSDAY, SATURDAY)

    for dates in (
        {"starts_on": THURSDAY},
        {"ends_on": SATURDAY},
        {"starts_on": "not-a-date", "ends_on": SATURDAY},
        {"starts_on": SATURDAY, "ends_on": THURSDAY},
    ):
        with pytest.raises(AgentError):
            validate_shifts([dict(_shift(1, 1), **dates)])
