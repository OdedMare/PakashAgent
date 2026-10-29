"""The רבעון: four groups, each closing one weekend in four."""

import datetime

import pytest

from app.bl import rotation
from app.bl.profile_service.roster import validate_rotation_groups
from app.bl.profile_service.workplace import workplace
from app.bl.scheduler import effective_availability
from app.common.errors import AgentError


def profile(mode="round"):
    return {
        "workplace": {"rotation_mode": mode, "quad_first_closure_date": "2026-08-29",
                      "quad_first_closure_group": "א"},
        "employees": [dict(name=group, exit_pattern="quad", rotation_group=group)
                      for group in ("א", "ב", "ג", "ד")],
        "shifts": [dict(name="בוקר", start_time="08:00", end_time="16:00", days=[])],
    }


def test_each_group_closes_one_weekend_in_four():
    p = profile()
    saturdays = [datetime.date(2026, 8, 29) + datetime.timedelta(days=7 * week) for week in range(5)]
    assert [rotation.closing_group(p, day, "quad") for day in saturdays] == ["א", "ב", "ג", "ד", "א"]


def test_only_the_closing_group_holds_its_weekend():
    p = profile()
    held = {row["employee"] for row in effective_availability(p, [], "2026-09-12", "2026-09-12")
            if row.get("source") in ("rotation", "closure")}
    # The weekend of 12/09 is ג's: everyone else is home.
    assert held == {"א", "ב", "ד"}


def test_the_preview_walks_all_four_groups():
    weeks = rotation.weekend_preview(profile(), "quad", datetime.date(2026, 8, 29), 4)
    assert [week["label"] for week in weeks] == ["רבעון א", "רבעון ב", "רבעון ג", "רבעון ד"]


def test_a_letter_names_its_cycle():
    assert rotation.cycle_of_group(profile(), "ד") == "quad"
    assert rotation.cycle_of_group(profile(), "ג") == "triplet"
    assert rotation.cycle_of_group(profile("quad"), "ג") == "quad"


def test_setup_accepts_a_quad_and_refuses_a_fifth_group():
    saved = workplace({"enabled_exit_patterns": ["quad"], "quad_first_closure_date": "2026-08-29"})
    assert saved["enabled_exit_patterns"] == ["quad"]
    p = profile()
    validate_rotation_groups(p)
    p["employees"][0]["rotation_group"] = "ה"
    with pytest.raises(AgentError):
        validate_rotation_groups(p)
