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
