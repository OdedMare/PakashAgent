"""The scenario profiles under `devsandbox/scenarios/` still load and solve.

`devsandbox/seed_scenario.py` saves them through `PUT /api/profile`, so a
scenario the validators have since outgrown would only fail on the evening
somebody sits down to use it. Saved here through the same `ProfileService`
and solved over the period the scenario's guide walks through.
"""

import importlib.util
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


def _read(name):
    return json.loads((_SCENARIOS / name).read_text(encoding="utf-8"))


def _save(profile):
    return ProfileService(_Repo()).update("team", **profile)


def _saved(name):
    return _save(_read(name))


def _is_split(name):
    """A split file (`seed_complex.py`) names a base profile to cut into
    משמרות; it is not a profile itself."""
    return "base" in _read(name)


def _seed_complex():
    spec = importlib.util.spec_from_file_location(
        "seed_complex", _SCENARIOS.parent / "seed_complex.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FILES = sorted(path.name for path in _SCENARIOS.glob("*.json"))


@pytest.mark.parametrize("name", [name for name in _FILES if not _is_split(name)])
def test_a_scenario_saves_through_the_profile_validators(name):
    saved = _saved(name)
    assert saved["employees"] and saved["shifts"]


@pytest.mark.parametrize("name", [name for name in _FILES if _is_split(name)])
def test_every_unit_of_a_split_saves_through_the_profile_validators(name):
    plan = _read(name)
    profiles = _seed_complex().split(_read(plan["base"]), plan["units"])
    assert [unit for unit, _ in profiles] == [unit["name"] for unit in plan["units"]]
    for unit, profile in profiles:
        saved = _save(profile)
        assert saved["workplace"]["name"] == unit
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
