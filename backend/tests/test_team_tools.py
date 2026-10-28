"""The range questions: who works, who carried the most, who is away, who
can shadow whom. Over unit 619's scenario profile, so the day cycle, the
roles and the trainees are the real ones."""

import pytest

from app.bl.tools import (
    TOOL_SHADOW_PARTNERS, TOOL_WHO_IS_AWAY, TOOL_WHO_WORKS, TOOL_WORKLOAD_RANKING,
    ScheduleTools,
)
from test_scenarios import _saved

TEAM = "team"


class _Repo:
    def __init__(self, profile, assignments, availability=()):
        self.profile = profile
        self.schedule = {"id": "p1", "team_id": TEAM, "starts_on": "2026-11-08",
                         "ends_on": "2026-11-14", "status": "draft", "slots": [],
                         "assignments": list(assignments)}
        self.rows = list(availability)

    def team_profile(self, team_id):
        return self.profile if team_id == TEAM else None

    def list_schedules(self, team_id):
        return [self.schedule] if team_id == TEAM else []

    def get_schedule(self, schedule_id, team_id):
        return self.schedule

    def current_schedule(self, team_id, published_only=False):
        return self.schedule

    def availability(self, team_id, starts_on=None, ends_on=None, employee=None):
        return [row for row in self.rows
                if (not starts_on or row["constraint_date"] >= starts_on)
                and (not ends_on or row["constraint_date"] <= ends_on)]


def _row(employee, shift, date):
    return {"employee": employee, "shift": shift, "date": date}


ROWS = [
    _row("עמית", "פריצה יום", "2026-11-09"), _row("שלומי", "פריצה יום", "2026-11-09"),
    _row("עמית", "פריצה יום", "2026-11-10"), _row("פיני", "פריצה לילה", "2026-11-10"),
    _row("עמית", "פריצה לילה", "2026-11-11"), _row("אילון", "פריצה יום", "2026-11-11"),
    _row("עדו", "חנית", "2026-11-09"), _row("גוןגון", "סופה יום", "2026-11-09"),
]


@pytest.fixture
def tools():
    return ScheduleTools(_Repo(_saved("unit_619.json"), ROWS, [{
        "employee": "עודד", "constraint_date": "2026-11-10", "shift_name": "",
        "available": False, "is_hard": True, "reason": "חולה",
    }]))


def test_who_works_lists_a_day_by_shift(tools):
    answer = tools.run(TEAM, TOOL_WHO_WORKS, {"day": "2026-11-09"})

    assert answer["ok"] and answer["found"]
    assert answer["people"] == sorted(["עמית", "שלומי", "עדו", "גוןגון"])
    shifts = {row["shift"]: row["employees"] for row in answer["days"][0]["shifts"]}
    assert shifts["פריצה יום"] == ["עמית", "שלומי"]


def test_who_works_filters_a_shift_over_a_range_and_refuses_an_unknown_one(tools):
    answer = tools.run(TEAM, TOOL_WHO_WORKS, {
        "starts_on": "2026-11-08", "ends_on": "2026-11-14", "shift_name": "פריצה לילה"})
    assert answer["people"] == ["עמית", "פיני"]

    unknown = tools.run(TEAM, TOOL_WHO_WORKS, {"day": "2026-11-09", "shift_name": "בוקר"})
    assert unknown["found"] is False and "פריצה יום" in unknown["shifts"]


def test_workload_ranking_is_sorted_names_ties_and_keeps_zeros(tools):
    answer = tools.run(TEAM, TOOL_WORKLOAD_RANKING, {
        "starts_on": "2026-11-08", "ends_on": "2026-11-14", "role": "פריצה", "top": 3})

    assert [row["employee"] for row in answer["ranking"]][:1] == ["עמית"]
    assert answer["ranking"][0]["shifts"] == 3 and answer["ranking"][0]["nights"] == 1
    assert answer["tied_for_most"] == ["עמית"]
    assert answer["considered"] == 9  # every פריצה soldier, the idle ones included
    assert len(answer["ranking"]) == 3


def test_workload_ranking_narrows_to_commanders_and_to_one_shift(tools):
    commanders = tools.run(TEAM, TOOL_WORKLOAD_RANKING, {
        "starts_on": "2026-11-08", "ends_on": "2026-11-14", "commanders_only": True})
    assert {row["employee"] for row in commanders["ranking"]} <= {"עדו", "עומר", "אילון", "גוןגון"}
    assert sorted(commanders["tied_for_most"]) == ["אילון", "גוןגון", "עדו"]

    nights = tools.run(TEAM, TOOL_WORKLOAD_RANKING, {
        "starts_on": "2026-11-08", "ends_on": "2026-11-14", "shift_name": "פריצה לילה"})
    assert sorted(nights["tied_for_most"]) == ["עמית", "פיני"]


def test_who_is_away_separates_the_cycle_from_a_recorded_absence(tools):
    sick = tools.run(TEAM, TOOL_WHO_IS_AWAY, {"day": "2026-11-10"})
    assert sick["days"][0]["away"] == [{
        "employee": "עודד", "whole_day": True, "kind": "constraint",
        "shifts": [], "reasons": ["חולה"],
    }]

    weekend = tools.run(TEAM, TOOL_WHO_IS_AWAY, {"day": "2026-11-14"})
    away = {row["employee"]: row for row in weekend["days"][0]["away"]}
    group_a = {p["name"] for p in _saved("unit_619.json")["employees"] if p["rotation_group"] == "א"}
    assert set(away) == group_a
    assert all(row["kind"] == "cycle" and row["whole_day"] for row in away.values())


def test_shadow_partners_reads_both_directions(tools):
    harel = tools.run(TEAM, TOOL_SHADOW_PARTNERS, {"employee": "הראל"})
    assert harel["is_trainee"] and [row["employee"] for row in harel["partners"]] == ["עומר"]

    shira = tools.run(TEAM, TOOL_SHADOW_PARTNERS, {"employee": "שירה"})
    assert {row["employee"] for row in shira["partners"]} == {"עדו", "עומר", "אילון", "גוןגון"}

    omer = tools.run(TEAM, TOOL_SHADOW_PARTNERS, {"employee": "עומר"})
    assert {row["employee"] for row in omer["partners"]} == {"הראל", "שירה", "אופיר"}


def test_a_range_needs_a_date_and_an_ambiguous_name_is_named_back(tools):
    assert tools.run(TEAM, TOOL_WHO_WORKS, {})["ok"] is False
    omers = tools.run(TEAM, TOOL_SHADOW_PARTNERS, {"employee": "עומר ע"})
    assert omers["found"] and omers["employee"] == "עומר עזורי"
