"""The constraint solver: fast, repeatable and rotation-safe (D34)."""

import pytest

from app.bl.solver import generate_day, generate_span
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
    assert result["metrics"]["engine"] == "solver"
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
    assert result["metrics"]["engine"] == "solver"
    assert result["metrics"]["total_tokens"] == 0


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


def test_a_slot_needing_a_rare_role_is_filled_before_a_broadly_staffed_one():
    # The evening has fewer legal people overall, but the morning's medic can
    # come from one person only; filling the evening first spent them there.
    profile = {
        "workplace": {"name": "יחידה"},
        "employees": [
            {"name": "אבי", "roles": ["חובש"]},
            {"name": "בני"},
            {"name": "גדי", "eligible_shifts": ["בוקר"]},
            {"name": "דני", "eligible_shifts": ["בוקר"]},
        ],
        "shifts": [
            {"name": "בוקר", "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": ["חובש"]}]},
            {"name": "ערב", "start_time": "15:00", "end_time": "23:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
        ],
    }

    result = generate_day(profile, "2026-08-30")

    placed = {row["shift"]: row["employee"] for row in result["assignments"]}
    assert placed == {"בוקר": "אבי", "ערב": "בני"}
    assert result["warnings"] == []


def _plain(people, headcount=1, **extra):
    profile = {
        "workplace": {"name": "יחידה"},
        "employees": people,
        "shifts": [{
            "name": SHIFT, "start_time": "07:00", "end_time": "15:00", "days": [],
            "staffing": [{"days": [], "headcount": headcount, "required_roles": []}],
        }],
    }
    profile.update(extra)
    return profile


def test_the_whole_span_is_solved_at_once_where_a_day_by_day_fill_runs_dry():
    """אבי alone may work the second day; one day at a time would spend him
    on the first, then find nobody for the second."""
    profile = _plain([{"name": "אבי"}, {"name": "בני"}],
                     audit_policy={"max_consecutive_days": 1})
    absent = [{"employee": "בני", "date": "2026-09-01", "available": False}]

    result = generate_span(profile, "2026-08-31", "2026-09-01", availability=absent)

    placed = {row["date"]: row["employee"] for row in result["assignments"]}
    assert placed == {"2026-08-31": "בני", "2026-09-01": "אבי"}
    assert result["warnings"] == []


def test_weekly_hours_are_a_ceiling_not_a_suggestion():
    profile = _plain([{"name": "אבי", "max_weekly_hours": 16}, {"name": "בני"}])

    result = generate_span(profile, "2026-08-31", "2026-09-04")

    worked = [row for row in result["assignments"] if row["employee"] == "אבי"]
    assert len(worked) <= 2
    assert len(result["assignments"]) == 5


def test_an_impossible_seat_is_reported_not_refused():
    profile = _plain([{"name": "אבי"}], headcount=2)

    result = generate_span(profile, "2026-08-31", "2026-08-31")

    assert [row["employee"] for row in result["assignments"]] == ["אבי"]
    assert any("נשארה בחוסר" in note for note in result["notes"])
    assert [item["code"] for item in result["warnings"]] == ["unfilled"]


def test_a_pin_stands_and_every_row_carries_a_reason():
    profile = _plain([{"name": "אבי"}, {"name": "בני"}])
    pin = {"employee": "בני", "shift": SHIFT, "date": "2026-08-31", "reason": "ביקש המנהל"}

    result = generate_span(profile, "2026-08-31", "2026-09-01", required_assignments=[pin])

    first = [row for row in result["assignments"] if row["date"] == "2026-08-31"]
    assert first == [dict(pin)]
    assert all(row["reason"] for row in result["assignments"])


def test_rows_outside_the_rebuilt_shifts_stay_and_count():
    profile = _plain([{"name": "אבי"}, {"name": "בני"}])
    profile["shifts"].append({
        "name": "לילה", "start_time": "23:00", "end_time": "07:00", "days": [],
        "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
    })
    night = {"employee": "אבי", "shift": "לילה", "date": "2026-08-30", "reason": "קיים"}

    result = generate_day(profile, "2026-08-31", shift_names=[SHIFT], already_scheduled=[night])

    assert [row["employee"] for row in result["assignments"]] == ["בני"]


def _dates(first, count):
    import datetime
    start = datetime.date.fromisoformat(first)
    return [(start + datetime.timedelta(days=step)).isoformat() for step in range(count)]


def test_a_soft_wish_is_not_broken_for_one_shift_of_evenness():
    """Eight people, eight days, one seat: אבי asked softly for the week off.
    Someone else working twice is cheaper than breaking the wish, however
    large the team."""
    names = ["אבי", "בני", "גדי", "דני", "הדר", "ורד", "זיו", "חן"]
    days = _dates("2026-08-30", 8)
    wish = [{"employee": "אבי", "date": day, "available": False, "is_hard": False,
             "reason": "חופשה"} for day in days]

    result = generate_span(_plain([{"name": name} for name in names]), days[0], days[-1],
                           availability=wish)

    assert "אבי" not in _counts(result["assignments"])
    assert len(result["assignments"]) == 8
    assert result["notes"] == []


def test_the_excess_over_part_timers_is_shared_not_handed_to_a_small_wish():
    """Two part-timers can take one shift a week; the rest falls on two
    people above an even share. A slight preference must not hand it all to
    one of them."""
    people = [{"name": "אבי"}, {"name": "בני"},
              {"name": "גדי", "max_weekly_hours": 8}, {"name": "דני", "max_weekly_hours": 8}]
    profile = _plain(people, headcount=2,
                     audit_policy={"max_consecutive_days": 30, "max_weekly_hours": 80})
    days = _dates("2026-08-31", 14)
    slight = [{"kind": "prefer", "employees": ["אבי"], "weight": 0.05,
               "reason": "מבקש עוד משמרות"}]

    result = generate_span(profile, days[0], days[-1], requests=slight)

    counts = _counts(result["assignments"])
    assert counts["אבי"] == counts["בני"] == 12
    assert counts["גדי"] == counts["דני"] == 2


def test_water_fill_targets_respect_what_people_carry_and_can_take():
    from app.bl.solver.fairness import water_fill

    targets = water_fill({"א": 0, "ב": 0, "ג": 0, "ד": 50}, {"א": 100, "ב": 100, "ג": 10, "ד": 100}, 150)

    assert targets["ג"] == 10
    assert targets["ד"] == 50
    assert targets["א"] + targets["ב"] == 90
    assert abs(targets["א"] - targets["ב"]) <= 1
    assert sum(targets.values()) == 150
