import pytest

from app.bl.profile_service import ProfileService
from app.common.errors import AgentError


class _Repo:
    def __init__(self):
        self.profile = {
            "employees": [{"name": "דנה", "role": "נציגת שירות"}],
            "shifts": [{
                "name": "בוקר", "start_time": "07:00", "end_time": "15:00",
                "staffing": [{"days": [], "headcount": 2}],
            }],
            "rules": [{"text": "כלל שנשמר"}],
        }

    def team_profile(self, team_id):
        return self.profile

    def update_team_profile(self, team_id, profile):
        self.profile = profile
        return profile

    def create_team_profile(self, team_id, profile):
        self.profile = profile
        return profile


def test_manual_profile_edit_preserves_unedited_sections():
    repo = _Repo()
    result = ProfileService(repo).update(
        "team", employees=[{"name": "דנה", "role": "מנהלת"}, {"name": "מאיה"}]
    )
    assert [row["name"] for row in result["employees"]] == ["דנה", "מאיה"]
    assert result["shifts"][0]["name"] == "בוקר"
    assert result["rules"] == [{"text": "כלל שנשמר"}]


def test_shift_edit_validates_time_and_updates_default_headcount():
    repo = _Repo()
    result = ProfileService(repo).update("team", shifts=[{
        "name": "בוקר", "start_time": "08:00", "end_time": "16:00",
        "headcount": 3, "is_on_call": False,
    }])
    assert result["shifts"][0]["staffing"][0]["headcount"] == 3

    with pytest.raises(AgentError):
        ProfileService(repo).update("team", shifts=[{
            "name": "בוקר", "start_time": "25:00", "end_time": "07:00",
        }])


def test_existing_names_cannot_be_removed_or_renamed_by_a_patch():
    repo = _Repo()
    with pytest.raises(AgentError):
        ProfileService(repo).update("team", employees=[{"name": "מאיה"}])


def test_adding_employee_does_not_rewrite_shift_staffing():
    repo = _Repo()
    ProfileService(repo).apply_operations("team", [{
        "action": "add_employee",
        "target": "",
        "item": {"name": "מאיה", "eligible_shifts": ["בוקר"]},
    }])
    assert repo.profile["shifts"][0]["staffing"][0]["headcount"] == 2


def test_first_profile_can_be_created_entirely_by_hand():
    repo = _Repo()
    repo.profile = None

    result = ProfileService(repo).update(
        "team",
        workplace={
            "name": "פלוגה א", "planning_horizon": "שבוע",
            "operating_days": ["ראשון", "שני"],
            "rotation_mode": "triplet", "first_closure_group": "ג",
            "first_closure_date": "2026-08-30",
        },
        employees=[{
            "name": "דנה", "rotation_group": "ג",
            "service_type": "overlap", "counts_toward_staffing": False,
        }],
        shifts=[{
            "name": "חמ״ל", "shift_type": "overlap",
            "start_time": "08:00", "end_time": "16:00", "headcount": 2,
        }],
        rules=[{"text": "אין חפיפה אחרי לילה", "priority": "hard"}],
        audit_policy={
            "max_weekly_hours": 45, "max_consecutive_days": 6,
            "min_rest_hours": 8,
        },
    )

    assert result["workplace"]["rotation_mode"] == "triplet"
    assert result["employees"][0]["is_trainee"] is True
    assert result["shifts"][0]["staffing"][0]["headcount"] == 2
    assert result["shifts"][0]["shift_type"] == "overlap"
    assert result["completeness"]["complete"] is True


def test_rotation_group_must_match_the_selected_structure():
    repo = _Repo()
    with pytest.raises(AgentError):
        ProfileService(repo).update("team", workplace={
            "name": "פלוגה", "rotation_mode": "round",
            "first_closure_group": "ג", "first_closure_date": "2026-08-30",
        })


def test_exit_pattern_capabilities_and_notes_are_per_employee():
    repo = _Repo()
    result = ProfileService(repo).update("team", employees=[{
        "name": "דנה",
        "role": "לוחמת חמ״ל",
        "exit_pattern": "hamshushim",
        "rotation_group": "",
        "is_shift_manager": True,
        "can_train": True,
        "notes": "צריכה לצאת בחמישי מוקדם",
    }])

    employee = result["employees"][0]
    assert employee["exit_pattern"] == "hamshushim"
    # No group: out every Thursday to Saturday rather than on a turn.
    assert employee["rotation_group"] == ""
    assert employee["is_shift_manager"] is True
    assert employee["can_train"] is True
    assert employee["notes"] == "צריכה לצאת בחמישי מוקדם"


def test_a_span_pattern_keeps_a_group_because_that_is_what_makes_it_rotate():
    """חמשושים with a group closes only its group's weekends.

    The group used to be discarded for anything but round/triplet, which made
    the rotating case impossible to record: every חמשושים person came back
    out every single week.
    """
    repo = _Repo()
    result = ProfileService(repo).update("team", employees=[{
        "name": "דנה", "exit_pattern": "hamshushim", "rotation_group": "ב",
    }])

    assert result["employees"][0]["rotation_group"] == "ב"


def test_a_span_pattern_group_is_validated_against_the_units_cycle():
    """A round unit has no group ג to belong to, whatever the pattern."""
    repo = _Repo()
    with pytest.raises(AgentError):
        ProfileService(repo).update(
            "team",
            workplace={"name": "פלוגה", "rotation_mode": "round"},
            employees=[{
                "name": "דנה", "exit_pattern": "hamshushim",
                "rotation_group": "ג",
            }],
        )


def test_each_employee_rotation_group_is_validated_against_own_pattern():
    repo = _Repo()
    result = ProfileService(repo).update("team", employees=[{
        "name": "דנה", "exit_pattern": "triplet", "rotation_group": "ג",
    }])
    assert result["employees"][0]["rotation_group"] == "ג"

    with pytest.raises(AgentError):
        ProfileService(repo).update("team", employees=[{
            "name": "דנה", "exit_pattern": "round", "rotation_group": "ג",
        }])


def test_rotation_a_schedule_and_optional_patterns_share_the_workplace_profile():
    repo = _Repo()
    result = ProfileService(repo).update("team", workplace={
        "name": "פלוגה",
        "enabled_exit_patterns": ["triplet", "hamshushim"],
        "rotation_a_unavailability": [{
            "days": ["שני"], "shifts": ["בוקר"],
            "start_time": "08:00", "end_time": "12:00",
            "reason": "יציאה קבועה",
        }],
    })

    workplace = result["workplace"]
    assert workplace["enabled_exit_patterns"] == ["triplet", "hamshushim"]
    assert workplace["rotation_a_unavailability"] == [{
        "days": ["שני"], "shifts": ["בוקר"],
        "start_time": "08:00", "end_time": "12:00",
        "reason": "יציאה קבועה",
    }]


def test_rotation_configuration_rejects_unknown_patterns_and_bad_times():
    repo = _Repo()
    with pytest.raises(AgentError):
        ProfileService(repo).update("team", workplace={
            "enabled_exit_patterns": ["invented"],
        })
    with pytest.raises(AgentError):
        ProfileService(repo).update("team", workplace={
            "rotation_a_unavailability": [{"start_time": "29:00"}],
        })
