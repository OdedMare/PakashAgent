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
])
def test_roster_refuses_unknown_values(field):
    with pytest.raises(AgentError):
        employees([dict({"name": "א"}, **field)])
