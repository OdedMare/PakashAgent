"""A new soldier or a new shift joins the board without reshuffling it.

The client's ask: adding a person or a shift should fit them into the
schedule already built, keeping almost everything where it was. The solver
holds each existing row (`solver/stability.py`); the range job carries that
through (`keep_existing`); saving the profile starts it on every draft ahead
of today (`generation/absorb.py`).
"""

from collections import Counter

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import Guards
from app.api.routers import profile as profile_router
from app.api.routers import schedules
from app.bl.schedule_service import ScheduleService
from app.bl.schedule_service.generation.absorb import added_to
from app.bl.solver import generate_span
from app.common.sessions import COOKIE_NAME, ROLE_BOSS, issue

from tests.test_schedule_api import SECRET, TEAM, _DeferredLauncher, _FakeScheduleRepo, _ScriptedLlm

MORNING, EVENING, NIGHT = "בוקר", "ערב", "לילה"
_TIMES = {MORNING: ("07:00", "15:00"), EVENING: ("15:00", "23:00"), NIGHT: ("23:00", "07:00")}
WEEK = ("2026-11-01", "2026-11-07")
SOLDIERS = ["א", "ב", "ג", "ד", "ה", "ו"]
# Enough people to staff a night too, rest rules and all.
PLATOON = SOLDIERS + ["ז", "ח", "ט", "י"]


def _profile(names=SOLDIERS, shifts=(MORNING, EVENING), headcount=2):
    return {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": name, "eligible_shifts": []} for name in names],
        "shifts": [{
            "name": name, "start_time": _TIMES[name][0], "end_time": _TIMES[name][1],
            "days": [], "staffing": [{"days": [], "headcount": headcount, "required_roles": []}],
        } for name in shifts],
        "rules": [],
    }


def _key(row):
    return row["employee"], row["shift"], row["date"]


def _moved(before, after):
    return len({_key(row) for row in before} - {_key(row) for row in after})


# -- the solver --------------------------------------------------------------

def test_a_new_soldier_takes_only_what_the_overloaded_carry():
    board = generate_span(_profile(), *WEEK)["assignments"]

    fresh = generate_span(_profile(SOLDIERS + ["ז"]), *WEEK)["assignments"]
    kept = generate_span(_profile(SOLDIERS + ["ז"]), *WEEK, keep=board)

    load = Counter(row["employee"] for row in kept["assignments"])
    assert load["ז"] == 4 and max(load.values()) == 4
    # 28 seats over six soldiers is four fives and two fours: the newcomer's
    # even share is four, so exactly the four fives give one each.
    assert _moved(board, kept["assignments"]) == 4
    assert _moved(board, fresh) > 4
    assert kept["metrics"]["kept"] == 24 and kept["metrics"]["moved"] == 4
    assert "הוטמע בסידור הקיים" in kept["notes"][0]


def test_a_new_shift_is_filled_around_the_rows_already_there():
    board = generate_span(_profile(PLATOON), *WEEK)["assignments"]
    grown = _profile(PLATOON, shifts=(MORNING, EVENING, NIGHT))

    fresh = generate_span(grown, *WEEK)["assignments"]
    kept = generate_span(grown, *WEEK, keep=board)["assignments"]

    assert len([row for row in kept if row["shift"] == NIGHT]) == 14
    assert _moved(board, kept) == 0
    assert _moved(board, fresh) > 0


def test_a_kept_row_keeps_the_reason_it_was_placed_with():
    board = [dict(row, reason="סיבה מקורית")
             for row in generate_span(_profile(), *WEEK)["assignments"]]

    kept = generate_span(_profile(SOLDIERS + ["ז"]), *WEEK, keep=board)["assignments"]

    stayed = [row for row in kept if _key(row) in {_key(item) for item in board}]
    assert stayed and {row["reason"] for row in stayed} == {"סיבה מקורית"}


# -- the range job -----------------------------------------------------------

def _service():
    repo = _FakeScheduleRepo()
    repo.profiles[TEAM] = _profile()
    launcher = _DeferredLauncher()
    service = ScheduleService(repo, _ScriptedLlm(), launch=launcher, sleep=lambda _s: None)
    return service, repo, launcher


def _built_week(service):
    opened = service.start_generation(TEAM, starts_on=WEEK[0], ends_on=WEEK[1])
    service.generate_next(TEAM, opened["id"])
    return service.get(opened["id"], TEAM)


def test_a_range_job_keeping_the_board_absorbs_a_new_soldier():
    service, repo, _ = _service()
    week = _built_week(service)
    repo.profiles[TEAM] = _profile(SOLDIERS + ["ז"])

    service.start_range_generation(TEAM, week["id"], *WEEK, keep_existing=True)
    after = service.generate_next(TEAM, week["id"])

    assert after["generation"]["keep_existing"] is True
    assert Counter(row["employee"] for row in after["assignments"])["ז"] == 4
    assert _moved(week["assignments"], after["assignments"]) == 4


def test_a_range_job_keeping_the_board_adds_the_new_shift_to_the_grid():
    service, repo, _ = _service()
    repo.profiles[TEAM] = _profile(PLATOON)
    week = _built_week(service)
    repo.profiles[TEAM] = _profile(PLATOON, shifts=(MORNING, EVENING, NIGHT))

    service.start_range_generation(TEAM, week["id"], "2026-11-04", WEEK[1], keep_existing=True)
    after = service.generate_next(TEAM, week["id"])

    nights = {row["slot_date"] for row in after["slots"] if row["shift_name"] == NIGHT}
    assert nights == {"2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"}
    assert len([row for row in after["assignments"] if row["shift"] == NIGHT]) == 8
    assert _moved(week["assignments"], after["assignments"]) == 0


# -- saving the profile ------------------------------------------------------

def test_what_a_save_added_is_new_active_people_and_new_shifts():
    before = _profile()
    after = _profile(SOLDIERS + ["ז"], shifts=(MORNING, NIGHT))
    after["employees"][0]["inactive_from"] = "2026-11-01"

    assert added_to(before, after) == {"employees": ["ז"], "shifts": [NIGHT]}
    assert added_to(None, after) == {"employees": [], "shifts": []}


def test_a_save_refits_drafts_ahead_and_lists_published_weeks():
    service, repo, launcher = _service()
    draft = _built_week(service)
    published = service.start_generation(TEAM, starts_on="2026-11-08", ends_on="2026-11-14")
    service.generate_next(TEAM, published["id"])
    repo.set_schedule_status(published["id"], TEAM, "published")
    service._absorber._today = lambda: "2026-11-03"
    before = repo.team_profile(TEAM)
    repo.profiles[TEAM] = _profile(SOLDIERS + ["ז"])

    result = service.absorb_profile_change(TEAM, before, repo.team_profile(TEAM))

    assert result["employees"] == ["ז"]
    assert result["schedules"] == [
        {"schedule_id": draft["id"], "starts_on": "2026-11-03", "ends_on": WEEK[1]}]
    assert [row["schedule_id"] for row in result["skipped"]] == [published["id"]]
    launcher.run_next()
    after = service.get(draft["id"], TEAM)
    assert after["generation"]["status"] == "complete"
    early = [row for row in draft["assignments"] if row["date"] < "2026-11-03"]
    assert _moved(early, after["assignments"]) == 0
    assert "ז" in {row["employee"] for row in after["assignments"]}


def test_a_new_shift_gets_its_row_on_an_empty_draft_without_a_build():
    service, repo, launcher = _service()
    blank = service.create_blank(TEAM, *WEEK)
    service._absorber._today = lambda: "2026-11-03"
    before = repo.team_profile(TEAM)
    repo.profiles[TEAM] = _profile(shifts=(MORNING, EVENING, NIGHT))

    result = service.absorb_profile_change(TEAM, before, repo.team_profile(TEAM))

    assert result["schedules"] == [] and result["skipped"] == [] and launcher.jobs == []
    nights = {row["slot_date"] for row in service.get(blank["id"], TEAM)["slots"]
              if row["shift_name"] == NIGHT}
    assert nights == {"2026-11-0%d" % day for day in range(3, 8)}


def test_a_save_that_adds_nobody_touches_no_draft():
    service, repo, launcher = _service()
    _built_week(service)

    result = service.absorb_profile_change(TEAM, _profile(), _profile())

    assert result["schedules"] == [] and launcher.jobs == []


class _Profiles:
    def __init__(self):
        self.saved = _profile()

    def current(self, team_id):
        return _profile()

    def update(self, team_id, **patch):
        return dict(self.saved, **patch)


class _Schedules:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def absorb_profile_change(self, team_id, before, after):
        self.calls.append((team_id, before, after))
        if self.fail:
            raise RuntimeError("down")
        return {"employees": ["ז"], "shifts": [], "schedules": [], "skipped": []}


def _profile_client(schedules_service):
    app = FastAPI()
    app.include_router(profile_router.build_router(_Profiles(), Guards(SECRET), schedules_service))
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, issue(SECRET, TEAM, ROLE_BOSS, 30))
    return client


def test_saving_the_profile_reports_what_was_absorbed():
    absorber = _Schedules()

    body = _profile_client(absorber).put("/api/profile", json={"summary": "x"}).json()

    assert body["absorbed"]["employees"] == ["ז"]
    assert absorber.calls[0][0] == TEAM


def test_a_refit_that_cannot_start_does_not_fail_the_save():
    response = _profile_client(_Schedules(fail=True)).put("/api/profile", json={"summary": "x"})

    assert response.status_code == 200
    assert response.json()["absorbed"] is None
