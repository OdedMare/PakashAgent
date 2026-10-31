"""The חמישון (1ל5): five groups, each closing one weekend in five."""

import datetime

import pytest

from app.bl import rotation
from app.bl.profile_service.roster import validate_rotation_groups
from app.bl.profile_service.workplace import workplace
from app.bl.scheduler import effective_availability
from app.bl.solver import generate_span
from app.common.errors import AgentError

GROUPS = ("א", "ב", "ג", "ד", "ה")


def profile(mode="round"):
    return {
        "workplace": {"rotation_mode": mode, "quint_first_closure_date": "2026-08-29",
                      "quint_first_closure_group": "א"},
        "employees": [dict(name=group, exit_pattern="quint", rotation_group=group)
                      for group in GROUPS],
        "shifts": [dict(name="בוקר", start_time="08:00", end_time="16:00", days=[])],
    }


def test_each_group_closes_one_weekend_in_five():
    p = profile()
    saturdays = [datetime.date(2026, 8, 29) + datetime.timedelta(days=7 * week) for week in range(6)]
    assert [rotation.closing_group(p, day, "quint") for day in saturdays] == list(GROUPS) + ["א"]


def test_only_the_closing_group_holds_its_weekend():
    p = profile()
    held = {row["employee"] for row in effective_availability(p, [], "2026-09-19", "2026-09-19")
            if row.get("source") in ("rotation", "closure")}
    # The weekend of 19/09 is ד's: everyone else is home.
    assert held == {"א", "ב", "ג", "ה"}


def test_the_solver_puts_only_the_closing_group_on_its_weekend():
    result = generate_span(profile(), "2026-09-26", "2026-09-26")
    assert {row["employee"] for row in result["assignments"]} == {"ה"}


def test_the_preview_walks_all_five_groups():
    weeks = rotation.weekend_preview(profile(), "quint", datetime.date(2026, 8, 29), 5)
    assert [week["label"] for week in weeks] == ["חמישון %s" % group for group in GROUPS]


def test_a_letter_names_its_cycle():
    assert rotation.cycle_of_group(profile(), "ה") == "quint"
    assert rotation.cycle_of_group(profile(), "ד") == "quad"
    assert rotation.cycle_of_group(profile("quint"), "ד") == "quint"
    assert rotation.cycle_of_group(profile("quint"), "ג") == "quint"
    assert rotation.cycle_of_group(profile("quad"), "ג") == "quad"


def test_an_unanchored_quint_cannot_be_scheduled():
    p = profile()
    p["workplace"]["quint_first_closure_date"] = ""
    assert any("חמישון" in error for error in rotation.configuration_errors(p))


def test_setup_accepts_a_quint_and_refuses_a_sixth_group():
    saved = workplace({"enabled_exit_patterns": ["quint"], "quint_first_closure_date": "2026-08-29"})
    assert saved["enabled_exit_patterns"] == ["quint"]
    p = profile()
    validate_rotation_groups(p)
    p["employees"][0]["rotation_group"] = "ו"
    with pytest.raises(AgentError):
        validate_rotation_groups(p)
