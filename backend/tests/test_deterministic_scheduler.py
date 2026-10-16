"""The outage fallback: fast, repeatable and rotation-safe.

The model assigns (D3); this engine runs only when it cannot be reached.
"""

import pytest

from app.bl.deterministic_scheduler import generate_day, generate_span, unsupported_reason
from app.common.errors import AgentError


SHIFT = "בוקר"


def _profile():
    return {
        "workplace": {
            "name": "יחידה",
            "round_first_closure_date": "2026-08-29",
            "round_first_closure_group": "א",
            "triplet_first_closure_date": "2026-08-29",
            "triplet_first_closure_group": "ג",
        },
        "employees": [
            {
                "name": "סבב א", "exit_pattern": "round",
                "rotation_group": "א", "eligible_shifts": [SHIFT],
                "is_shift_manager": True,
            },
            {
                "name": "סבב ב", "exit_pattern": "round",
                "rotation_group": "ב", "eligible_shifts": [SHIFT],
                "is_shift_manager": True,
            },
            {
                "name": "תלתון ג", "exit_pattern": "triplet",
                "rotation_group": "ג", "eligible_shifts": [SHIFT],
            },
            {
                "name": "תלתון א", "exit_pattern": "triplet",
                "rotation_group": "א", "eligible_shifts": [SHIFT],
            },
        ],
        "shifts": [{
            "name": SHIFT,
            "start_time": "07:00",
            "end_time": "15:00",
            "days": [],
            "requires_shift_manager": True,
            "staffing": [{
                "days": [], "headcount": 2, "required_roles": [],
            }],
        }],
    }


def test_saturday_uses_the_round_and_triplet_groups_that_close_it():
    result = generate_day(_profile(), "2026-08-29")

    assert [row["employee"] for row in result["assignments"]] == [
        "סבב א", "תלתון ג",
    ]
    assert result["metrics"]["engine"] == "deterministic"
    assert result["metrics"]["total_tokens"] == 0
    assert result["warnings"] == []


def test_declared_rotation_without_an_anchor_blocks_generation():
    profile = _profile()
    profile["workplace"]["triplet_first_closure_date"] = ""

    with pytest.raises(AgentError, match="תלתון"):
        generate_day(profile, "2026-08-29")


def test_span_builds_each_day_in_code_without_tokens():
    result = generate_span(_profile(), "2026-08-29", "2026-08-30")

    assert {row["date"] for row in result["assignments"]} == {
        "2026-08-29", "2026-08-30",
    }
    assert result["metrics"]["engine"] == "code"
    assert result["metrics"]["total_tokens"] == 0


def test_semantic_inputs_are_not_silently_sent_to_code():
    profile = dict(_profile(), rules=[{"text": "תעדף את דנה", "priority": "soft"}])

    assert "AI" in unsupported_reason(profile)


def _counts(assignments, shift=None):
    counts = {}
    for row in assignments:
        if shift is None or row["shift"] == shift:
            counts[row["employee"]] = counts.get(row["employee"], 0) + 1
    return counts


def test_nights_are_spread_rather_than_given_to_the_lightest_in_hours():
    people = ["אבי", "בני", "גדי", "דני", "הדר", "ורד"]
    profile = {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": name} for name in people],
        "shifts": [
            {"name": "בוקר", "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": 2, "required_roles": []}]},
            {"name": "לילה", "start_time": "23:00", "end_time": "07:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
        ],
    }

    result = generate_span(profile, "2026-08-30", "2026-09-10")

    nights = _counts(result["assignments"], "לילה")
    assert sum(nights.values()) == 12
    assert max(nights.values()) - min(nights.get(name, 0) for name in people) <= 1


def test_open_days_lean_away_from_the_group_closing_the_coming_weekend():
    """ב closes Thursday to Saturday; Monday to Wednesday should go to א, or
    ב ends the week carrying both the weekdays and its own closure."""
    profile = {
        "workplace": {
            "name": "יחידה",
            "round_first_closure_date": "2026-08-29",
            "round_first_closure_group": "א",
        },
        "employees": [
            {"name": name, "exit_pattern": "round", "rotation_group": group}
            for name, group in (("א1", "א"), ("א2", "א"), ("ב1", "ב"), ("ב2", "ב"))
        ],
        "shifts": [{
            "name": SHIFT, "start_time": "07:00", "end_time": "15:00", "days": [],
            "staffing": [{"days": [], "headcount": 2, "required_roles": []}],
        }],
    }

    result = generate_span(profile, "2026-08-31", "2026-09-05")

    shifts = _counts(result["assignments"])
    assert sum(shifts.values()) == 12
    assert max(shifts.values()) - min(shifts.values()) <= 1


def test_equal_load_is_spread_with_a_day_off_between_assignments():
    profile = {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": "אבי"}, {"name": "בני"}],
        "shifts": [{
            "name": SHIFT, "start_time": "07:00", "end_time": "15:00", "days": [],
            "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
        }],
    }
    history = [
        {"employee": "אבי", "shift": SHIFT, "date": "2026-08-30"},
        {"employee": "בני", "shift": SHIFT, "date": "2026-08-21"},
    ]

    result = generate_day(profile, "2026-08-31", history=history)

    assert [row["employee"] for row in result["assignments"]] == ["בני"]


def test_previous_period_night_protects_eight_hours_of_rest():
    profile = {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": "אבי"}],
        "shifts": [
            {"name": SHIFT, "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
            {"name": "לילה", "start_time": "23:00", "end_time": "07:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
        ],
    }

    result = generate_day(
        profile, "2026-08-31", shift_names=[SHIFT],
        history=[{"employee": "אבי", "shift": "לילה", "date": "2026-08-30"}],
    )

    assert result["assignments"] == []
    assert "נשארה בחוסר" in result["notes"][0]
