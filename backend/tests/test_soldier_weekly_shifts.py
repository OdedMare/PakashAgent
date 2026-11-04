"""A soldier's own weekly minimum and maximum of shifts, over their service
type's in the unit standard — read by the solver and the audit alike."""

from collections import Counter

import pytest

from app.bl.audit import audit
from app.bl.audit.unit_policy import weekly_limits
from app.bl.profile_service import roster
from app.bl.solver import generate_span
from app.common.errors import AgentError

DAY = "יום"
SUNDAY, SATURDAY = "2026-11-08", "2026-11-14"


def _person(name, **extra):
    return dict({"name": name, "exit_pattern": "none", "rotation_group": "",
                 "eligible_shifts": [DAY]}, **extra)


def _profile(people, policy=None):
    return {
        "workplace": {"name": "יחידה"},
        "employees": people,
        "shifts": [{"name": DAY, "start_time": "08:00", "end_time": "20:00",
                    "staffing": [{"days": [], "headcount": 1, "required_roles": []}]}],
        "unit_policy": policy or {},
    }


def _load(result):
    return Counter(row["employee"] for row in result["assignments"])


def test_a_soldiers_own_numbers_win_each_on_its_own():
    profile = _profile([], {"weekly_shifts_regular": {"min": 2, "max": 5},
                            "weekly_shifts": {"min": 1, "max": 3}})

    assert weekly_limits(profile, {"service_type": "standard", "max_weekly_shifts": 3}) == (2, 3)
    assert weekly_limits(profile, {"service_type": "standard", "min_weekly_shifts": 0}) == (0, 5)
    assert weekly_limits(profile, {"service_type": "reserve", "min_weekly_shifts": 2,
                                   "max_weekly_shifts": None}) == (2, 3)
    assert weekly_limits(_profile([]), {"max_weekly_shifts": 4}) == (0, 4)


def test_the_solver_holds_a_soldier_to_their_own_maximum():
    people = [_person("דנה", max_weekly_shifts=2), _person("רון")]
    result = generate_span(_profile(people, {"weekly_shifts_regular": {"max": 6}}), SUNDAY, SATURDAY)

    load = _load(result)
    assert load["דנה"] <= 2 and load["רון"] >= 5


def test_the_solver_gives_a_soldier_their_own_minimum():
    people = [_person("דנה", min_weekly_shifts=5), _person("רון"), _person("טל")]
    result = generate_span(_profile(people), SUNDAY, SATURDAY)

    assert _load(result)["דנה"] >= 5
    assert not any("פחות מהמינימום" in note for note in result["notes"])


def test_the_audit_warns_past_a_soldiers_own_maximum():
    people = [_person("דנה", max_weekly_shifts=2)]
    profile = _profile(people, {"weekly_shifts_regular": {"max": 6}})
    rows = [{"employee": "דנה", "shift": DAY, "date": "2026-11-%02d" % day} for day in range(8, 11)]

    over = [item for item in audit(rows, profile["shifts"], people, profile=profile)
            if item["code"] == "weekly_shifts"]
    assert [item["date"] for item in over] == ["2026-11-10"]


def test_the_roster_validates_and_clears_a_soldiers_limits():
    [person] = roster.employees([_person("דנה", min_weekly_shifts="2", max_weekly_shifts="")])
    assert person["min_weekly_shifts"] == 2 and person["max_weekly_shifts"] is None

    with pytest.raises(AgentError, match="גדול מהמקסימום"):
        roster.employees([_person("דנה", min_weekly_shifts=5, max_weekly_shifts=2)])
    with pytest.raises(AgentError, match="מספר"):
        roster.employees([_person("דנה", max_weekly_shifts="הרבה")])
