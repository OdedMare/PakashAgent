"""The scenario profiles under `devsandbox/scenarios/` still load and solve.

`devsandbox/seed_scenario.py` saves them through `PUT /api/profile`, so a
scenario the validators have since outgrown would only fail on the evening
somebody sits down to use it. Saved here through the same `ProfileService`
and solved over the period the scenario's guide walks through.
"""

import json
import pathlib

import pytest

from app.bl.profile_service import ProfileService
from app.bl.solver import generate_span

_SCENARIOS = pathlib.Path(__file__).resolve().parents[2] / "devsandbox" / "scenarios"


class _Repo:
    profile = None

    def team_profile(self, team_id):
        return self.profile

    def team_profile_revision(self, team_id):
        return None

    def create_team_profile(self, team_id, profile):
        self.profile = profile
        return profile


def _saved(name):
    raw = json.loads((_SCENARIOS / name).read_text(encoding="utf-8"))
    return ProfileService(_Repo()).update("team", **raw)


@pytest.mark.parametrize("name", sorted(path.name for path in _SCENARIOS.glob("*.json")))
def test_a_scenario_saves_through_the_profile_validators(name):
    saved = _saved(name)
    assert saved["employees"] and saved["shifts"]


def test_unit_619_closes_by_group_and_places_its_trainees():
    result = generate_span(_saved("unit_619.json"), "2026-11-01", "2026-11-15", time_limit=20)
    by_date = {}
    for row in result["assignments"]:
        by_date.setdefault(row["date"], set()).add(row["employee"])
    people = {person["name"]: person for person in _saved("unit_619.json")["employees"]}

    # 13-14.11 is group א's weekend home: only group ב stands it.
    for date in ("2026-11-13", "2026-11-14"):
        assert by_date[date]
        assert {people[name]["rotation_group"] for name in by_date[date]} == {"ב"}
    # The trainees with no team are placed, beside somebody, never in a seat.
    placed = {row["employee"] for row in result["assignments"]}
    assert {"שירה", "אופיר", "הראל"} <= placed
