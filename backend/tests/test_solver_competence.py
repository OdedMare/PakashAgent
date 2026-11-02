"""Reservists' days a week and shifts balanced by competence."""

import pytest

from app.bl.profile_service.roster import employees
from app.bl.solver import generate_span
from app.common.errors import AgentError

MORNING, EVENING = "בוקר", "ערב"


def _person(name, group="א", **fields):
    return dict({"name": name, "exit_pattern": "round", "rotation_group": group,
                 "eligible_shifts": [MORNING, EVENING]}, **fields)


def _profile(people, shifts=(MORNING,)):
    times = {MORNING: ("07:00", "15:00"), EVENING: ("15:00", "23:00")}
    return {
        "workplace": {"name": "יחידה", "round_first_closure_date": "2026-08-29",
                      "round_first_closure_group": "א"},
        "employees": people,
        "shifts": [{"name": name, "start_time": times[name][0], "end_time": times[name][1],
                    "days": [], "staffing": [{"days": [], "headcount": 2, "required_roles": []}]}
                   for name in shifts],
    }


def _worked(result, name):
    return {row["date"] for row in result["assignments"] if row["employee"] == name}


def test_a_reservist_works_no_more_days_than_they_come():
    people = [_person("דנה"), _person("יוסי", "ב"), _person("רון", "ב"),
              _person("מילואימניק", service_type="reserve", reserve_days_per_week=1)]
    result = generate_span(_profile(people), "2026-08-31", "2026-09-02")

    assert len(_worked(result, "מילואימניק")) == 1
    assert len(result["assignments"]) == 6


def test_the_cap_is_per_sunday_week_and_counts_fixed_days():
    people = [_person("דנה"), _person("יוסי", "ב"),
              _person("מילואימניק", service_type="reserve", reserve_days_per_week=1)]
    pinned = [{"employee": "מילואימניק", "shift": MORNING, "date": "2026-08-31"}]
    result = generate_span(_profile(people), "2026-08-31", "2026-09-02",
                           required_assignments=pinned)

    assert _worked(result, "מילואימניק") == {"2026-08-31"}


def test_a_standard_soldier_ignores_reserve_days():
    people = [_person("דנה", reserve_days_per_week=1), _person("יוסי", "ב")]
    result = generate_span(_profile(people), "2026-08-31", "2026-09-02")

    assert len(_worked(result, "דנה")) == 3


def test_weak_soldiers_are_not_staffed_together():
    people = [_person("חלש1", competence="weak"), _person("חלש2", "ב", competence="weak"),
              _person("חזק1", competence="excellent"), _person("חזק2", "ב", competence="excellent")]
    result = generate_span(_profile(people, (MORNING, EVENING)), "2026-08-31", "2026-08-31")

    assert len(result["assignments"]) == 4
    for shift in (MORNING, EVENING):
        crew = {row["employee"] for row in result["assignments"] if row["shift"] == shift}
        assert len([name for name in crew if name.startswith("חלש")]) == 1, crew


def test_roster_keeps_reserve_answers_only_for_reservists():
    rows = employees([
        {"name": "א", "service_type": "reserve", "reserve_days_per_week": "3",
         "reserve_call": "order", "competence": "high"},
        {"name": "ב", "service_type": "standard", "reserve_days_per_week": 3,
         "reserve_call": "days"},
    ])

    assert (rows[0]["reserve_days_per_week"], rows[0]["reserve_call"], rows[0]["competence"]) \
        == (3, "order", "high")
    assert (rows[1]["reserve_days_per_week"], rows[1]["reserve_call"], rows[1]["competence"]) \
        == (None, "", "")


@pytest.mark.parametrize("field", [
    {"competence": "great"},
    {"service_type": "reserve", "reserve_days_per_week": 8},
    {"service_type": "reserve", "reserve_call": "maybe"},
    {"service_type": "reserve", "reserve_min_days": 0},
    {"service_type": "reserve", "reserve_days_per_week": 2, "reserve_min_days": 3},
    {"service_type": "reserve", "reserve_consecutive": "yes"},
])
def test_roster_refuses_unknown_values(field):
    with pytest.raises(AgentError):
        employees([dict({"name": "א"}, **field)])


# -- a dynamic reservist: how many days, and in one block ------------------

WEEK = ("2026-08-30", "2026-09-05")  # Sunday to Saturday


def _one_seat(people):
    profile = _profile(people)
    profile["shifts"][0]["staffing"][0]["headcount"] = 1
    return profile


def _regulars():
    return [_person(name, group) for name, group in
            (("דנה", "א"), ("יוסי", "ב"), ("רון", "א"), ("מיכל", "ב"), ("עדי", "א"))]


def _reservist(**fields):
    return _person("מילואימניק", service_type="reserve", **fields)


def test_a_reservist_with_a_minimum_comes_that_many_days():
    people = _regulars() + [_reservist(reserve_days_per_week=3, reserve_min_days=3)]
    result = generate_span(_one_seat(people), *WEEK)

    assert len(_worked(result, "מילואימניק")) == 3


def test_without_a_minimum_evenness_decides():
    people = _regulars() + [_reservist(reserve_days_per_week=3)]
    result = generate_span(_one_seat(people), *WEEK)

    assert len(_worked(result, "מילואימניק")) < 3


def test_consecutive_days_form_one_block():
    people = _regulars() + [_reservist(reserve_days_per_week=3, reserve_min_days=3,
                                       reserve_consecutive=True)]
    result = generate_span(_one_seat(people), *WEEK)

    days = sorted(_worked(result, "מילואימניק"))
    assert len(days) == 3
    ordinals = [int(day[-2:]) if day >= "2026-09-01" else int(day[-2:]) - 31 for day in days]
    assert ordinals == list(range(ordinals[0], ordinals[0] + 3)), days


def test_a_week_cut_by_the_span_owes_no_minimum():
    people = _regulars() + [_reservist(reserve_days_per_week=3, reserve_min_days=3)]
    result = generate_span(_one_seat(people), "2026-08-30", "2026-09-01")

    assert not any("מילואים" in note for note in result["notes"])


def test_fixed_days_around_a_gap_stay_feasible():
    people = _regulars() + [_reservist(reserve_days_per_week=3, reserve_consecutive=True)]
    pinned = [{"employee": "מילואימניק", "shift": MORNING, "date": "2026-08-30"},
              {"employee": "מילואימניק", "shift": MORNING, "date": "2026-09-01"}]
    result = generate_span(_one_seat(people), *WEEK, required_assignments=pinned)

    worked = _worked(result, "מילואימניק")
    assert {"2026-08-30", "2026-09-01"} <= worked
    # Nothing past the block: the third day, if any, is the gap closed.
    assert worked <= {"2026-08-30", "2026-08-31", "2026-09-01"}


def test_roster_keeps_minimum_and_block_only_for_reservists():
    rows = employees([
        {"name": "א", "service_type": "reserve", "reserve_days_per_week": 3,
         "reserve_min_days": "2", "reserve_consecutive": True},
        {"name": "ב", "service_type": "standard", "reserve_min_days": 2,
         "reserve_consecutive": True},
    ])

    assert (rows[0]["reserve_min_days"], rows[0]["reserve_consecutive"]) == (2, True)
    assert (rows[1]["reserve_min_days"], rows[1]["reserve_consecutive"]) == (None, False)
