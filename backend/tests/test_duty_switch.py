"""The on/off switch: a soldier switched off is not taken into account at all.

Reservists come and go. `on_duty: false` keeps them on the roster — their
name, history and colour — and out of every build: the solver never places
them, a hand placement is refused, and switching them off frees their draft
shifts from today on for a refit to fill. Switching them back on fits them
in like a new soldier.
"""

from collections import Counter

import pytest

from app.bl.placement.values import is_eligible
from app.bl.profile_service.roster import employees
from app.bl.schedule_service.generation.absorb import OFF_DUTY_CHANGE, added_to, turned_off
from app.bl.scheduler.availability import OFF_DUTY_REASON, effective_availability
from app.bl.shared import out_of_service, switched_off
from app.bl.solver import generate_span
from app.common.errors import AgentError

from tests.test_absorb import SOLDIERS, WEEK, _built_week, _profile, _service
from tests.test_schedule_api import TEAM


def _off(profile, *names):
    for person in profile["employees"]:
        if person["name"] in names:
            person["on_duty"] = False
    return profile


def test_only_an_explicit_false_switches_a_soldier_off():
    assert not switched_off({"name": "א"})
    assert not switched_off({"name": "א", "on_duty": True})
    assert switched_off({"name": "א", "on_duty": False})
    assert out_of_service({"name": "א", "on_duty": False}, "2026-11-01")
    assert out_of_service({"name": "א", "inactive_from": "2026-11-01"}, "2026-11-02")
    assert not out_of_service({"name": "א", "inactive_from": "2026-11-03"}, "2026-11-02")


def test_the_roster_keeps_the_switch_and_defaults_it_on():
    rows = employees([{"name": "א"}, {"name": "ב", "on_duty": False}, {"name": "ג", "on_duty": "no"}])

    assert [row["on_duty"] for row in rows] == [True, False, True]


def test_a_switched_off_soldier_is_unavailable_every_day_of_a_build():
    profile = _off(_profile(), "א")

    rows = [row for row in effective_availability(profile, [], *WEEK) if row["employee"] == "א"]

    assert len(rows) == 7 and all(row["is_hard"] and not row["available"] for row in rows)
    assert {row["reason"] for row in rows} == {OFF_DUTY_REASON}


def test_the_solver_never_places_a_switched_off_soldier():
    board = generate_span(_off(_profile(), "א", "ב"), *WEEK)["assignments"]

    load = Counter(row["employee"] for row in board)
    assert "א" not in load and "ב" not in load
    # Everyone else still shares the week evenly: 28 seats over four.
    assert sorted(load.values()) == [7, 7, 7, 7]


def test_the_placement_check_says_no_to_a_switched_off_soldier():
    profile = _off(_profile(), "א")

    assert not is_eligible(profile, "א", "בוקר", "2026-11-02")
    assert is_eligible(profile, "ב", "בוקר", "2026-11-02")


def test_a_hand_placement_of_a_switched_off_soldier_is_refused():
    service, repo, _ = _service()
    blank = service.create_blank(TEAM, *WEEK)
    _off(repo.profiles[TEAM], "א")

    with pytest.raises(AgentError, match="כבוי"):
        service.assign(TEAM, "בוקר", "2026-11-02", "א", schedule_id=blank["id"])


def test_what_a_save_switched_off_and_back_on():
    before = _profile()
    after = _off(_profile(), "א")

    assert turned_off(before, after) == ["א"]
    assert added_to(before, after) == {"employees": [], "shifts": []}
    # Back on reads as a new soldier, so the refit fits them in.
    assert added_to(after, _profile()) == {"employees": ["א"], "shifts": []}
    assert turned_off(None, after) == []


def test_switching_off_vacates_draft_shifts_from_today_and_refits():
    service, repo, launcher = _service()
    draft = _built_week(service)
    service._absorber._today = lambda: "2026-11-03"
    before = repo.team_profile(TEAM)
    repo.profiles[TEAM] = _off(_profile(), "א")

    result = service.absorb_profile_change(TEAM, before, repo.team_profile(TEAM))

    held = [row for row in draft["assignments"]
            if row["employee"] == "א" and row["date"] >= "2026-11-03"]
    assert result["switched_off"] == ["א"] and result["vacated"] == len(held) > 0
    assert result["schedules"] == [
        {"schedule_id": draft["id"], "starts_on": "2026-11-03", "ends_on": WEEK[1]}]
    removed = [row for row in repo.changes if row["action"] == "removed"]
    assert len(removed) == len(held) and {row["reason"] for row in removed} == {OFF_DUTY_CHANGE}
    launcher.run_next()
    after = service.get(draft["id"], TEAM)
    later = [row for row in after["assignments"] if row["date"] >= "2026-11-03"]
    assert "א" not in {row["employee"] for row in later}
    # Every seat ahead is filled again by the others; the past is untouched.
    assert len(later) == len([row for row in draft["assignments"] if row["date"] >= "2026-11-03"])
    early = sorted((row["employee"], row["shift"], row["date"])
                   for row in draft["assignments"] if row["date"] < "2026-11-03")
    assert sorted((row["employee"], row["shift"], row["date"])
                  for row in after["assignments"] if row["date"] < "2026-11-03") == early


def test_switching_off_takes_hand_placed_rows_too():
    service, repo, launcher = _service()
    blank = service.create_blank(TEAM, *WEEK)
    service.assign(TEAM, "בוקר", "2026-11-05", "א", schedule_id=blank["id"])
    service.assign(TEAM, "בוקר", "2026-11-05", "ב", schedule_id=blank["id"])
    service._absorber._today = lambda: "2026-11-03"
    before = repo.team_profile(TEAM)
    repo.profiles[TEAM] = _off(_profile(), "א")

    result = service.absorb_profile_change(TEAM, before, repo.team_profile(TEAM))

    assert result["vacated"] == 1
    launcher.run_next()
    after = service.get(blank["id"], TEAM)
    assert after["generation"]["status"] == "complete"
    assert "א" not in {row["employee"] for row in after["assignments"]}
    assert ("ב", "בוקר", "2026-11-05") in {
        (row["employee"], row["shift"], row["date"]) for row in after["assignments"]}


def test_switching_off_leaves_a_published_week_and_says_so():
    service, repo, launcher = _service()
    week = _built_week(service)
    repo.set_schedule_status(week["id"], TEAM, "published")
    service._absorber._today = lambda: "2026-11-03"
    before = repo.team_profile(TEAM)
    repo.profiles[TEAM] = _off(_profile(), "א")

    result = service.absorb_profile_change(TEAM, before, repo.team_profile(TEAM))

    assert result["vacated"] == 0 and launcher.jobs == []
    assert [row["schedule_id"] for row in result["skipped"]] == [week["id"]]
    assert service.get(week["id"], TEAM)["assignments"] == week["assignments"]


def test_switching_off_someone_with_no_shifts_ahead_touches_no_draft():
    service, repo, launcher = _service()
    _built_week(service)
    service._absorber._today = lambda: "2026-11-30"
    before = repo.team_profile(TEAM)
    repo.profiles[TEAM] = _off(_profile(), "א")

    result = service.absorb_profile_change(TEAM, before, repo.team_profile(TEAM))

    assert result["schedules"] == [] and result["vacated"] == 0 and launcher.jobs == []


def test_switching_back_on_fits_the_soldier_into_the_drafts():
    service, repo, launcher = _service()
    repo.profiles[TEAM] = _off(_profile(), "א")
    draft = _built_week(service)
    assert "א" not in {row["employee"] for row in draft["assignments"]}
    service._absorber._today = lambda: "2026-11-01"
    before = repo.team_profile(TEAM)
    repo.profiles[TEAM] = _profile(SOLDIERS)

    result = service.absorb_profile_change(TEAM, before, repo.team_profile(TEAM))

    assert result["employees"] == ["א"]
    launcher.run_next()
    after = service.get(draft["id"], TEAM)
    assert Counter(row["employee"] for row in after["assignments"])["א"] == 4
