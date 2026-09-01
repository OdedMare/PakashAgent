"""The read-only tools the agent runs, over a fake repository.

Table-driven where the shape allows, like `test_placement.py`, and for the
same reason: these are pure reads over state, so the contract is expressible
as fixtures in and facts out.

Four things here are the point of the feature and are asserted directly:

- **No tool writes.** The repository fake counts every mutating call it has,
  and the count stays zero across every tool in the menu.
- **Nothing is invented.** An unknown employee comes back `found: False`
  carrying the real roster, never a plausible substitute.
- **A replacement candidate has been checked.** Everything `find_replacements`
  offers is re-validated by `placement.py`, so an option that would warn is
  never presented as a way out of a warning.
- **One workspace cannot read another's period**, even holding its id (D10).
"""

import pytest

from app.bl.tools import (
    TOOL_COVERAGE_GAPS,
    TOOL_EMPLOYEE_STATE,
    TOOL_FIND_REPLACEMENTS,
    TOOL_NAMES,
    TOOL_PROFILE_GAPS,
    TOOL_PUBLISH_READINESS,
    TOOL_READ_PERIOD,
    TOOL_TEAM_OVERVIEW,
    TOOL_VALIDATE_PLACEMENT,
    ScheduleTools,
)
from app.common.errors import NotFoundError

TEAM = "team-a"
OTHER_TEAM = "team-b"

MORNING = "בוקר"
EVENING = "צהריים"

DANA = "דנה"
YOSSI = "יוסי"
RON = "רון"

PROFILE = {
    "workplace": {"name": "מוקד"},
    "employees": [
        {"name": DANA, "role": "מוקדנית", "eligible_shifts": [MORNING]},
        {"name": YOSSI, "role": "מוקדן", "eligible_shifts": [MORNING, EVENING]},
        {"name": RON, "role": "מוקדן", "eligible_shifts": [MORNING, EVENING]},
    ],
    "shifts": [
        {
            "name": MORNING, "start_time": "07:00", "end_time": "15:00",
            "days": [], "is_on_call": False, "hour_weight": 1.0,
            "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
        },
        {
            "name": EVENING, "start_time": "15:00", "end_time": "23:00",
            "days": [], "is_on_call": False, "hour_weight": 1.0,
            "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
        },
    ],
    "rules": [],
}


class _Repo:
    """An in-memory repository that filters by team exactly as the SQL does.

    Counts writes so the tests can assert that reading is *all* the tool
    layer does. A tool that wrote would be a second path to a change, and
    the product deliberately has one.
    """

    def __init__(self):
        self.writes = 0
        self.profiles = {TEAM: PROFILE, OTHER_TEAM: PROFILE}
        self.schedules = {}
        self.availability_rows = []
        self.pending = []

    # -- the reads the tools use -------------------------------------------

    def team_profile(self, team_id):
        return self.profiles.get(team_id)

    def get_schedule(self, schedule_id, team_id):
        row = self.schedules.get(schedule_id)
        if row is None or row["team_id"] != team_id:
            raise NotFoundError("הפריט לא נמצא")
        return row

    def list_schedules(self, team_id):
        return [
            {k: row[k] for k in ("id", "starts_on", "ends_on", "status")}
            for row in self.schedules.values() if row["team_id"] == team_id
        ]

    def current_schedule(self, team_id, published_only=False):
        for row in reversed(list(self.schedules.values())):
            if row["team_id"] != team_id:
                continue
            if published_only and row["status"] != "published":
                continue
            return row
        return None

    def availability(self, team_id, starts_on=None, ends_on=None, employee=None):
        return [
            row for row in self.availability_rows
            if row["team_id"] == team_id
            and (not starts_on or row["constraint_date"] >= starts_on)
            and (not ends_on or row["constraint_date"] <= ends_on)
        ]

    def pending_constraint_requests(self, team_id):
        return [row for row in self.pending if row["team_id"] == team_id]

    # -- writes, which no tool may reach -----------------------------------

    def add_assignment(self, *args, **kwargs):
        self.writes += 1

    def remove_assignment(self, *args, **kwargs):
        self.writes += 1

    def move_assignment(self, *args, **kwargs):
        self.writes += 1

    def append_change(self, *args, **kwargs):
        self.writes += 1

    def set_availability(self, *args, **kwargs):
        self.writes += 1


def _schedule(repo, team_id=TEAM, schedule_id="sched-1", assignments=None):
    """A two-shift, two-day period with whoever the test puts on it."""
    slots = []
    for date in ("2026-08-17", "2026-08-18"):
        for shift in (MORNING, EVENING):
            slots.append({
                "id": "slot-%s-%s" % (shift, date),
                "shift_name": shift, "slot_date": date,
                "start_time": "07:00" if shift == MORNING else "15:00",
                "end_time": "15:00" if shift == MORNING else "23:00",
                "headcount": 1, "is_on_call": False,
            })
    rows = []
    for index, item in enumerate(assignments or []):
        rows.append({
            "id": "asg-%d" % index,
            "slot_id": "slot-%s-%s" % (item["shift"], item["date"]),
            "employee": item["employee"],
            "shift": item["shift"],
            "date": item["date"],
            "reason": "בדיקה",
            "source": "agent",
        })
    repo.schedules[schedule_id] = {
        "id": schedule_id, "team_id": team_id,
        "starts_on": "2026-08-17", "ends_on": "2026-08-18",
        "status": "draft", "slots": slots, "assignments": rows,
    }
    return repo.schedules[schedule_id]


@pytest.fixture
def repo():
    return _Repo()


@pytest.fixture
def tools(repo):
    return ScheduleTools(repo)


# -- nothing writes --------------------------------------------------------


def test_no_tool_writes_anything(repo, tools):
    """The property the whole layer rests on: these read and nothing else."""
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    for name in TOOL_NAMES:
        tools.run(TEAM, name, {
            "employee": DANA, "shift_name": MORNING,
            "slot_date": "2026-08-17",
        })
    assert repo.writes == 0


# -- reading a period ------------------------------------------------------


def test_read_period_returns_the_current_one(repo, tools):
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    answer = tools.run(TEAM, TOOL_READ_PERIOD, {})
    assert answer["ok"] and answer["found"]
    assert answer["schedule"]["starts_on"] == "2026-08-17"
    assert answer["schedule"]["assignment_count"] == 1


def test_read_period_returns_computed_round_and_triplet_closures(repo, tools):
    repo.profiles[TEAM] = {
        **PROFILE,
        "workplace": {
            "name": "מוקד",
            "round_first_closure_date": "2026-08-22",
            "round_first_closure_group": "א",
            "triplet_first_closure_date": "2026-08-22",
            "triplet_first_closure_group": "ג",
        },
        "employees": [
            {"name": DANA, "exit_pattern": "round", "rotation_group": "א"},
            {"name": YOSSI, "exit_pattern": "triplet", "rotation_group": "ג"},
        ],
    }
    schedule = _schedule(repo)
    schedule["ends_on"] = "2026-08-23"

    answer = tools.run(TEAM, TOOL_READ_PERIOD, {})

    assert answer["closures"][0]["closing_groups"] == [
        {"pattern": "round", "group": "א"},
        {"pattern": "triplet", "group": "ג"},
    ]


def test_read_period_by_date_finds_the_covering_period(repo, tools):
    _schedule(repo)
    answer = tools.run(TEAM, TOOL_READ_PERIOD, {"day": "2026-08-18"})
    assert answer["found"] and answer["schedule"]["id"] == "sched-1"


def test_relative_dates_never_reach_an_individual_scheduling_tool(tools):
    answer = tools.run(TEAM, TOOL_READ_PERIOD, {"day": "tomorrow"})

    assert answer["ok"] is False
    assert "YYYY-MM-DD" in answer["error"]


def test_an_absolute_israel_date_and_timezone_are_accepted(repo, tools):
    _schedule(repo)

    answer = tools.run(TEAM, TOOL_READ_PERIOD, {
        "day": "2026-08-17", "timezone": "Asia/Jerusalem",
    })

    assert answer["ok"] is True
    assert answer["schedule"]["starts_on"] == "2026-08-17"


def test_a_date_no_period_covers_is_not_found(repo, tools):
    _schedule(repo)
    answer = tools.run(TEAM, TOOL_READ_PERIOD, {"day": "2027-01-01"})
    assert answer["found"] is False
    assert answer["reason"]


def test_no_schedule_at_all_is_an_answer_not_an_error(tools):
    """An empty workspace is an ordinary state, not a failure."""
    answer = tools.run(TEAM, TOOL_READ_PERIOD, {})
    assert answer["ok"] and answer["found"] is False


def test_team_overview_returns_declared_people_and_roles(tools):
    answer = tools.run(TEAM, TOOL_TEAM_OVERVIEW, {})
    assert answer["found"] and answer["employee_count"] == 3
    assert answer["employees"][0] == {
        "name": DANA,
        "role": "מוקדנית",
        "eligible_shifts": [MORNING],
    }
    assert answer["shift_count"] == 2


# -- one employee ----------------------------------------------------------


def test_employee_state_reports_their_shifts_and_hours(repo, tools):
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
        {"employee": DANA, "shift": MORNING, "date": "2026-08-18"},
    ])
    answer = tools.run(TEAM, TOOL_EMPLOYEE_STATE, {"employee": DANA})
    assert answer["found"]
    assert len(answer["shifts"]) == 2
    assert answer["hours"] == 16.0
    assert answer["role"] == "מוקדנית"
    assert answer["eligible_shifts"] == [MORNING]


def test_an_unknown_employee_is_not_invented(repo, tools):
    """The specific failure this shape exists to make impossible."""
    _schedule(repo)
    answer = tools.run(TEAM, TOOL_EMPLOYEE_STATE, {"employee": "מישהו"})
    assert answer["found"] is False
    # The real roster comes back so the agent can ask against real names.
    assert set(answer["roster"]) == {DANA, YOSSI, RON}


def test_employee_state_without_a_name_is_a_refusal(tools):
    answer = tools.run(TEAM, TOOL_EMPLOYEE_STATE, {})
    assert answer["ok"] is False and answer["error"]


def test_employee_constraints_come_back_with_them(repo, tools):
    _schedule(repo)
    repo.availability_rows.append({
        "team_id": TEAM, "employee": DANA, "constraint_date": "2026-08-18",
        "shift_name": "", "available": False, "reason": "לימודים",
        "source": "manager",
    })
    answer = tools.run(TEAM, TOOL_EMPLOYEE_STATE, {"employee": DANA})
    assert len(answer["constraints"]) == 1
    assert answer["constraints"][0]["reason"] == "לימודים"


# -- gaps ------------------------------------------------------------------


def test_coverage_gaps_finds_the_empty_slots(repo, tools):
    """An unstaffed slot leaves no assignment row — the grid is what sees it."""
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    answer = tools.run(TEAM, TOOL_COVERAGE_GAPS, {})
    assert answer["found"]
    # Four slots, one filled.
    assert answer["total_gaps"] == 3
    assert answer["people_short"] == 3


def test_coverage_gaps_narrow_to_a_day(repo, tools):
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    answer = tools.run(TEAM, TOOL_COVERAGE_GAPS, {
        "starts_on": "2026-08-17", "ends_on": "2026-08-17",
    })
    assert answer["total_gaps"] == 1
    assert answer["gaps"][0]["shift"] == EVENING


def test_a_full_period_reports_no_gaps(repo, tools):
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
        {"employee": YOSSI, "shift": EVENING, "date": "2026-08-17"},
        {"employee": RON, "shift": MORNING, "date": "2026-08-18"},
        {"employee": YOSSI, "shift": EVENING, "date": "2026-08-18"},
    ])
    answer = tools.run(TEAM, TOOL_COVERAGE_GAPS, {})
    assert answer["total_gaps"] == 0 and answer["gaps"] == []


def test_a_trainee_shadowing_a_shift_does_not_close_its_gap(repo, tools):
    """The gap list counts seats, not bodies — `audit.py`'s rule.

    Somebody learning the shift is standing on it and is still not one of the
    people it asked for. Answering "no gaps" here would tell the manager a
    slot is covered by the one person there because they cannot yet cover it,
    and the audit under the same schedule would still call it short.
    """
    trainee = "מתלמד"
    repo.profiles[TEAM] = dict(PROFILE, employees=PROFILE["employees"] + [
        {"name": trainee, "role": "מוקדן", "is_trainee": True,
         "counts_toward_staffing": False},
    ])
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
        {"employee": trainee, "shift": EVENING, "date": "2026-08-17"},
    ])

    answer = tools.run(TEAM, TOOL_COVERAGE_GAPS, {
        "starts_on": "2026-08-17", "ends_on": "2026-08-17",
    })
    evening = [row for row in answer["gaps"] if row["shift"] == EVENING]
    assert len(evening) == 1
    assert evening[0]["assigned"] == 0 and evening[0]["missing"] == 1


# -- validating ------------------------------------------------------------


def test_validate_placement_never_blocks(repo, tools):
    """`blocking` is false however bad the news (D3)."""
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    answer = tools.run(TEAM, TOOL_VALIDATE_PLACEMENT, {
        "employee": DANA, "shift_name": MORNING, "slot_date": "2026-08-17",
    })
    assert answer["blocking"] is False


def test_validate_placement_reports_an_ineligible_shift(repo, tools):
    """דנה works mornings only, per the profile — not per a literal here."""
    _schedule(repo)
    answer = tools.run(TEAM, TOOL_VALIDATE_PLACEMENT, {
        "employee": DANA, "shift_name": EVENING, "slot_date": "2026-08-17",
    })
    assert answer["ok"] is False
    assert answer["eligible"] is False
    assert any(EVENING in reason for reason in answer["reasons"])


def test_a_clean_placement_validates(repo, tools):
    _schedule(repo)
    answer = tools.run(TEAM, TOOL_VALIDATE_PLACEMENT, {
        "employee": YOSSI, "shift_name": EVENING, "slot_date": "2026-08-17",
    })
    assert answer["ok"] is True and answer["reasons"] == []


# -- replacements ----------------------------------------------------------


def test_find_replacements_offers_qualified_free_colleagues(repo, tools):
    _schedule(repo, assignments=[
        {"employee": YOSSI, "shift": EVENING, "date": "2026-08-17"},
    ])
    answer = tools.run(TEAM, TOOL_FIND_REPLACEMENTS, {
        "employee": YOSSI, "shift_name": EVENING, "slot_date": "2026-08-17",
    })
    assert answer["found"]
    names = [row["employee"] for row in answer["candidates"]]
    # רון is qualified for evenings; דנה is not, and must not appear.
    assert RON in names
    assert DANA not in names


# A unit that closes, so the rotation has something to say about who may
# take a slot. 2026-08-29 is a Saturday and belongs to סבב א, which makes
# the weekend of 2026-08-15 א's as well — two cycles earlier.
UNIT_PROFILE = dict(
    PROFILE,
    workplace={
        "name": "פלוגה", "rotation_mode": "round",
        "first_closure_date": "2026-08-29", "first_closure_group": "א",
    },
    employees=[
        {"name": DANA, "role": "לוחמת", "eligible_shifts": [MORNING],
         "exit_pattern": "round", "rotation_group": "ב"},
        {"name": YOSSI, "role": "לוחם", "eligible_shifts": [MORNING, EVENING],
         "exit_pattern": "round", "rotation_group": "ב"},
        {"name": RON, "role": "לוחם", "eligible_shifts": [MORNING, EVENING],
         "exit_pattern": "round", "rotation_group": "א"},
    ],
)

CLOSURE_FRIDAY = "2026-08-14"


def _closure_schedule(repo, assignments=None):
    """The same two-shift period, on a weekend סבב א is holding."""
    slots = []
    for date in ("2026-08-13", CLOSURE_FRIDAY):
        for shift in (MORNING, EVENING):
            slots.append({
                "id": "slot-%s-%s" % (shift, date),
                "shift_name": shift, "slot_date": date,
                "start_time": "07:00" if shift == MORNING else "15:00",
                "end_time": "15:00" if shift == MORNING else "23:00",
                "headcount": 1, "is_on_call": False,
            })
    rows = []
    for index, item in enumerate(assignments or []):
        rows.append({
            "id": "asg-%d" % index,
            "slot_id": "slot-%s-%s" % (item["shift"], item["date"]),
            "employee": item["employee"], "shift": item["shift"],
            "date": item["date"], "reason": "בדיקה", "source": "agent",
        })
    repo.profiles[TEAM] = UNIT_PROFILE
    repo.schedules["sched-1"] = {
        "id": "sched-1", "team_id": TEAM,
        "starts_on": "2026-08-13", "ends_on": CLOSURE_FRIDAY,
        "status": "draft", "slots": slots, "assignments": rows,
    }
    return repo.schedules["sched-1"]


def test_a_borrow_is_offered_only_when_the_closing_group_is_empty(repo, tools):
    """רון is the only one whose weekend this is, and he is the one leaving.

    The answer is not "nobody". יוסי is on the other cycle, free and
    qualified, and asking him is a thing the manager can do — so he comes
    back separately, marked as needing their approval (D25).
    """
    _closure_schedule(repo, assignments=[
        {"employee": RON, "shift": EVENING, "date": CLOSURE_FRIDAY},
    ])
    answer = tools.run(TEAM, TOOL_FIND_REPLACEMENTS, {
        "employee": RON, "shift_name": EVENING, "slot_date": CLOSURE_FRIDAY,
    })

    assert answer["candidates"] == []
    assert [row["employee"] for row in answer["borrow"]] == [YOSSI]
    assert answer["borrow"][0]["requires_approval"] is True
    assert answer["borrow_note"]


def test_a_borrow_is_withheld_while_the_closing_group_can_answer(repo, tools):
    """A cross-rotation name beside a free colleague teaches the wrong thing.

    On an ordinary date every qualified colleague is simply available, and
    nothing needs anybody's permission.
    """
    _schedule(repo, assignments=[
        {"employee": YOSSI, "shift": EVENING, "date": "2026-08-17"},
    ])
    answer = tools.run(TEAM, TOOL_FIND_REPLACEMENTS, {
        "employee": YOSSI, "shift_name": EVENING, "slot_date": "2026-08-17",
    })

    assert answer["candidates"]
    assert answer["borrow"] == []
    assert answer["borrow_note"] == ""


def test_every_candidate_carries_its_reason(repo, tools):
    _schedule(repo, assignments=[
        {"employee": YOSSI, "shift": EVENING, "date": "2026-08-17"},
    ])
    answer = tools.run(TEAM, TOOL_FIND_REPLACEMENTS, {
        "employee": YOSSI, "shift_name": EVENING, "slot_date": "2026-08-17",
    })
    assert answer["candidates"]
    for row in answer["candidates"]:
        assert row["why"]
        assert "hours" in row
    # And the ranking says what it ranked on, in Hebrew.
    assert answer["ranked_by"]


def test_a_candidate_who_would_warn_is_never_offered(repo, tools):
    """The honesty property: an option that breaks something is not an option.

    רון is already on the morning of the 17th and a constraint bars him from
    the evening, so the only qualified colleague is filtered out and the
    answer is an empty list rather than a plausible name.
    """
    _schedule(repo, assignments=[
        {"employee": YOSSI, "shift": EVENING, "date": "2026-08-17"},
        {"employee": RON, "shift": MORNING, "date": "2026-08-17"},
    ])
    repo.availability_rows.append({
        "team_id": TEAM, "employee": RON, "constraint_date": "2026-08-17",
        "shift_name": "", "available": False, "reason": "לא זמין",
        "source": "manager",
    })
    answer = tools.run(TEAM, TOOL_FIND_REPLACEMENTS, {
        "employee": YOSSI, "shift_name": EVENING, "slot_date": "2026-08-17",
    })
    assert [row["employee"] for row in answer["candidates"]] == []


# -- publishing ------------------------------------------------------------


def test_publish_readiness_lists_what_is_open(repo, tools):
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
    ])
    answer = tools.run(TEAM, TOOL_PUBLISH_READINESS, {})
    assert answer["found"]
    assert answer["ready"] is False
    assert answer["blockers"]


def test_publish_readiness_is_descriptive_not_a_gate(repo, tools):
    """`ready: False` has never stopped a publish and must not start (D3)."""
    _schedule(repo)
    answer = tools.run(TEAM, TOOL_PUBLISH_READINESS, {})
    assert answer["ready"] is False
    # Status is reported as it stands; nothing here refuses anything.
    assert answer["status"] == "draft"
    assert answer["published"] is False


def test_a_full_period_with_nothing_pending_is_ready(repo, tools):
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
        {"employee": YOSSI, "shift": EVENING, "date": "2026-08-17"},
        {"employee": RON, "shift": MORNING, "date": "2026-08-18"},
        {"employee": YOSSI, "shift": EVENING, "date": "2026-08-18"},
    ])
    answer = tools.run(TEAM, TOOL_PUBLISH_READINESS, {})
    assert answer["ready"] is True and answer["blockers"] == []


def test_pending_requests_are_named_before_publishing(repo, tools):
    _schedule(repo, assignments=[
        {"employee": DANA, "shift": MORNING, "date": "2026-08-17"},
        {"employee": YOSSI, "shift": EVENING, "date": "2026-08-17"},
        {"employee": RON, "shift": MORNING, "date": "2026-08-18"},
        {"employee": YOSSI, "shift": EVENING, "date": "2026-08-18"},
    ])
    repo.pending.append({"team_id": TEAM, "id": "req-1", "employee": DANA})
    answer = tools.run(TEAM, TOOL_PUBLISH_READINESS, {})
    assert answer["ready"] is False
    assert len(answer["pending_requests"]) == 1


# -- workspace isolation ---------------------------------------------------


def test_another_workspace_period_reads_as_missing(repo, tools):
    """Holding the id is not access. A cross-team miss is just a miss (D10)."""
    _schedule(repo, team_id=OTHER_TEAM, schedule_id="theirs")
    answer = tools.run(TEAM, TOOL_READ_PERIOD, {"schedule_id": "theirs"})
    assert answer["found"] is False


def test_a_tool_reads_only_its_own_team_roster(repo, tools):
    _schedule(repo, team_id=OTHER_TEAM, schedule_id="theirs")
    _schedule(repo, team_id=TEAM, schedule_id="mine")
    answer = tools.run(TEAM, TOOL_READ_PERIOD, {})
    assert answer["schedule"]["id"] == "mine"


# -- the menu itself -------------------------------------------------------


def test_an_unknown_tool_is_an_answer_not_a_crash(tools):
    answer = tools.run(TEAM, "לא קיים", {})
    assert answer["ok"] is False and answer["error"]


def test_unknown_arguments_are_dropped_rather_than_crashing(repo, tools):
    """A model producing a stray argument name should not end the turn."""
    _schedule(repo)
    answer = tools.run(TEAM, TOOL_READ_PERIOD, {
        "day": "2026-08-17", "מה": "זה", "limit": 5,
    })
    assert answer["ok"] and answer["found"]


# -- what the interview never taught ---------------------------------------


def test_a_confirmed_profile_reports_nothing_outstanding(repo, tools):
    """No `completeness` key means the gate let it finish, so nothing is owed."""
    answer = tools.run(TEAM, TOOL_PROFILE_GAPS, {})
    assert answer["ok"] and answer["found"]
    assert answer["complete"] is True
    assert answer["gaps"] == []


def test_an_ended_interview_reports_what_it_still_owes(repo, tools):
    repo.profiles[TEAM] = dict(PROFILE, completeness={
        "complete": False,
        "missing_topics": ["חסרה תקופת התכנון של הסידור."],
        "open_points": ["לא נמסרו האילוצים הקבועים."],
    })
    answer = tools.run(TEAM, TOOL_PROFILE_GAPS, {})
    assert answer["complete"] is False
    assert answer["gaps"] == ["חסרה תקופת התכנון של הסידור."]
    assert answer["open_points"] == ["לא נמסרו האילוצים הקבועים."]


def test_a_gap_is_not_listed_twice(repo, tools):
    """`open_points` carries the missing topics too — the interview appends
    them there so the manager sees them mid-conversation. Reported once."""
    line = "לא נרשם אף עובד."
    repo.profiles[TEAM] = dict(PROFILE, completeness={
        "complete": False,
        "missing_topics": [line],
        "open_points": [line, "משהו אחר."],
    })
    answer = tools.run(TEAM, TOOL_PROFILE_GAPS, {})
    assert answer["gaps"] == [line]
    assert answer["open_points"] == ["משהו אחר."]


def test_a_missing_shift_vocabulary_blocks_even_manual_building(repo, tools):
    """The one gap that stops everything: D9 forbids inventing shift names,
    so with none declared there are no rows to fill by hand either."""
    repo.profiles[TEAM] = {
        "workplace": {"name": "מוקד"}, "shifts": [], "employees": [],
        "completeness": {"complete": False, "missing_topics": []},
    }
    answer = tools.run(TEAM, TOOL_PROFILE_GAPS, {})
    assert answer["has_shifts"] is False
    assert any("ידנית" in line for line in answer["blocks"])


def test_no_interview_at_all_is_an_answer_not_a_crash(repo, tools):
    repo.profiles.pop(TEAM)
    answer = tools.run(TEAM, TOOL_PROFILE_GAPS, {})
    assert answer["ok"] and answer["found"] is False
