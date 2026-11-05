"""How much a shift weighs when load is evened: a night counts more."""

import pytest

from app.bl.audit.roster import load_weight
from app.bl.profile_service.shifts import shifts as validate_shifts
from app.bl.solver import generate_span
from app.common.errors import AgentError


def _counts(assignments, shift=None):
    counts = {}
    for row in assignments:
        if shift is None or row["shift"] == shift:
            counts[row["employee"]] = counts.get(row["employee"], 0) + 1
    return counts


def _nights_and_mornings(night_weight=None):
    """אבי alone may stand the two nights; everyone may stand a morning."""
    night = {"name": "לילה", "start_time": "23:00", "end_time": "07:00",
             "days": ["ראשון", "שני"],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]}
    if night_weight is not None:
        night["load_weight"] = night_weight
    return {
        "workplace": {"name": "יחידה"},
        "employees": [
            {"name": "אבי", "eligible_shifts": ["לילה", "בוקר"]},
            {"name": "בני", "eligible_shifts": ["בוקר"]},
            {"name": "גדי", "eligible_shifts": ["בוקר"]},
        ],
        "shifts": [
            night,
            {"name": "בוקר", "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
        ],
    }


def test_a_night_weighs_one_and_a_half_by_default():
    assert load_weight({"start_time": "23:00", "end_time": "07:00"}) == 1.5
    assert load_weight({"start_time": "07:00", "end_time": "15:00"}) == 1.0
    assert load_weight({"is_night": True}) == 1.5


def test_an_on_call_night_is_not_a_night_worked():
    assert load_weight({"start_time": "23:00", "end_time": "07:00", "is_on_call": True}) == 1.0


def test_a_stated_weight_wins_over_the_default():
    assert load_weight({"start_time": "23:00", "end_time": "07:00", "load_weight": 1}) == 1.0
    assert load_weight({"start_time": "07:00", "end_time": "15:00", "load_weight": 1.25}) == 1.25
    # A value outside the list is not a weight the manager could have chosen.
    assert load_weight({"start_time": "07:00", "end_time": "15:00", "load_weight": 9}) == 1.0


def test_setup_keeps_a_listed_weight_and_refuses_another():
    saved = validate_shifts([{"name": "לילה", "load_weight": "1.5"}, {"name": "בוקר"}])
    assert [row["load_weight"] for row in saved] == [1.5, None]
    with pytest.raises(AgentError, match="משקל העומס"):
        validate_shifts([{"name": "לילה", "load_weight": 4}])


def test_whoever_carries_the_nights_carries_fewer_shifts():
    """Two nights (only אבי may take them) and six mornings. Counted one to
    a shift, אבי's two nights leave him a morning to reach an even share;
    weighed at 1.5 each, they already are his share."""
    result = generate_span(_nights_and_mornings(), "2026-08-30", "2026-09-04")

    assert _counts(result["assignments"], "לילה") == {"אבי": 2}
    assert "אבי" not in _counts(result["assignments"], "בוקר")
    assert _counts(result["assignments"], "בוקר") == {"בני": 3, "גדי": 3}


def test_a_night_weighed_as_one_shift_is_counted_as_before():
    result = generate_span(_nights_and_mornings(night_weight=1), "2026-08-30", "2026-09-04")

    assert _counts(result["assignments"], "בוקר").get("אבי") == 1


def test_one_night_of_evenness_stays_cheaper_than_a_soft_wish():
    """Moving the heaviest night from the most loaded to the least loaded
    person saves both distances and the peak, in shifts and in nights. It
    must stay below one soft wish, or a wish would be broken to even out
    one shift (`model.py`)."""
    from app.bl.audit.roster import LOAD_WEIGHTS
    from app.bl.solver.model import (
        NIGHT_PEAK, NIGHT_SCALE, NIGHT_SPREAD, SHIFT_PEAK, SHIFT_SCALE, SHIFT_SPREAD, WISH,
    )

    units = round(SHIFT_SCALE * max(LOAD_WEIGHTS))
    saved = units * (2 * SHIFT_SPREAD + SHIFT_PEAK) + NIGHT_SCALE * (2 * NIGHT_SPREAD + NIGHT_PEAK)
    assert saved < WISH
