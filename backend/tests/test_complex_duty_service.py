"""The commander's duty rules, with no database (`ComplexDutyService`).

The SQL guards are pinned in `test_complex_duties_postgres.py`; these pin
what the service decides before it writes: a soldier on the team's roster
and still serving, a type that is on and runs that weekday, a free seat --
and after: the change log as the commander, the team told, the shifts the
duty now blocks returned as a warning.
"""

import pytest

from app.bl.complex_duties import (
    ACTION_COMPLEX_DUTY, ACTION_COMPLEX_DUTY_CANCELLED, ACTION_COMPLEX_DUTY_RECORDED,
    ComplexDutyService,
)
from app.common.actor import current_actor
from app.common.errors import AgentError, ConflictError, NotFoundError

COMPLEX = "c-1"
TEAM = "t-1"
TUESDAY = "2026-11-10"
MONDAY = "2026-11-09"


class _Complexes:
    def describe(self, complex_id):
        return {"teams": [{"id": TEAM, "name": "משמרת א", "active": True}]}

    def require_team(self, complex_id, team_id):
        if complex_id == COMPLEX and team_id == TEAM:
            return {"id": TEAM, "name": "משמרת א", "active": True}
        raise NotFoundError("המשמרת לא נמצאה")


class _Repo:
    def __init__(self):
        self.types = {}
        self.duties = {}
        self.changes = []
        self.shifts = []
        self.profile = {"employees": [
            {"name": "דנה"}, {"name": "יוסי"},
            {"name": "רון", "inactive_from": "2026-11-05"},
        ]}

    def complex_duty_types(self, complex_id):
        return [t for t in self.types.values() if t["complex_id"] == complex_id]

    def create_complex_duty_type(self, complex_id, name, seats=1, days=None, weight=1):
        row = dict(id="dt-%d" % (len(self.types) + 1), complex_id=complex_id,
                   name=name, seats=seats, days=list(days or []), weight=weight,
                   active=True)
        self.types[row["id"]] = row
        return row

    def complex_duty_type(self, complex_id, type_id):
        row = self.types.get(type_id)
        if row is None or row["complex_id"] != complex_id:
            raise NotFoundError("סוג התורנות לא נמצא")
        return row

    def update_complex_duty_type(self, complex_id, type_id, fields):
        self.complex_duty_type(complex_id, type_id).update(fields)
        return self.types[type_id]

    def complex_duties(self, complex_id, starts_on, ends_on):
        return [d for d in self.duties.values()
                if starts_on <= d["duty_date"] <= ends_on]

    def set_complex_duty(self, complex_id, type_id, team_id, employee, duty_date, note="",
                         blocks=True):
        row = dict(blocks=blocks, id="d-%d" % (len(self.duties) + 1), complex_id=complex_id,
                   duty_type_id=type_id, duty_type=self.types[type_id]["name"],
                   team_id=team_id, employee=employee, duty_date=duty_date, note=note)
        self.duties[row["id"]] = row
        return row

    def delete_complex_duty(self, complex_id, duty_id):
        return self.duties.pop(duty_id)

    def soldier_shifts(self, team_id, employee, starts_on, ends_on):
        return [s for s in self.shifts
                if s["employee"] == employee and starts_on <= s["slot_date"] <= ends_on]

    def team_profile(self, team_id):
        return self.profile

    def append_change(self, team_id, action, **fields):
        self.changes.append(dict(fields, team_id=team_id, action=action,
                                 actor=current_actor()))


@pytest.fixture
def setup():
    repo, told = _Repo(), []
    service = ComplexDutyService(repo, _Complexes(),
                                 notify=lambda *args: told.append(args))
    kitchen = service.create_type(COMPLEX, {"name": "מטבח", "seats": 1})
    return service, repo, told, kitchen


def _shift(date, name, start, end, status="draft", schedule="s-1"):
    return dict(id="a-%s-%s" % (date, name), employee="דנה", slot_date=date, shift_name=name,
                start_time=start, end_time=end, status=status, schedule_id=schedule)


def test_assigning_logs_as_the_commander_tells_the_team_and_warns(setup):
    service, repo, told, kitchen = setup
    repo.shifts = [
        _shift(MONDAY, "בוקר", "07:00", "15:00"),
        _shift(MONDAY, "לילה", "23:00", "07:00", status="published"),
        _shift(TUESDAY, "ערב", "15:00", "23:00"),
    ]

    result = service.assign(COMPLEX, kitchen["id"], TEAM, " דנה ", TUESDAY, "מטבח מרכזי",
                            resolve=False)

    assert result["duty"]["employee"] == "דנה"
    assert [(c["date"], c["shift_name"], c["status"]) for c in result["conflicts"]] == [
        (MONDAY, "לילה", "published"), (TUESDAY, "ערב", "draft"),
    ]
    [change] = repo.changes
    assert change["action"] == ACTION_COMPLEX_DUTY
    assert change["actor"] == "commander:" + COMPLEX
    assert (change["employee"], change["slot_date"], change["reason"]) == (
        "דנה", TUESDAY, "מטבח מרכזי")
    assert told == [(TEAM, COMPLEX, "שיבץ תורנות מכלול")]


def test_cancelling_logs_and_tells_too(setup):
    service, repo, told, kitchen = setup
    duty = service.assign(COMPLEX, kitchen["id"], TEAM, "דנה", TUESDAY)["duty"]

    service.cancel(COMPLEX, duty["id"])

    assert repo.changes[-1]["action"] == ACTION_COMPLEX_DUTY_CANCELLED
    assert told[-1] == (TEAM, COMPLEX, "ביטל תורנות מכלול")


@pytest.mark.parametrize("employee, message", [
    ("אבי", "לא נמצא/ת ברשימת החיילים"),
    ("רון", "סיים/ה את השירות"),
])
def test_only_a_serving_soldier_of_that_team_is_seated(setup, employee, message):
    service, _, told, kitchen = setup

    with pytest.raises(AgentError, match=message):
        service.assign(COMPLEX, kitchen["id"], TEAM, employee, TUESDAY)
    assert told == []


def test_another_complexs_team_is_not_found(setup):
    service, _, _, kitchen = setup
    with pytest.raises(NotFoundError):
        service.assign(COMPLEX, kitchen["id"], "t-other", "דנה", TUESDAY)


def test_seats_weekdays_and_an_inactive_type_are_respected(setup):
    service, _, _, kitchen = setup
    service.assign(COMPLEX, kitchen["id"], TEAM, "דנה", TUESDAY)
    with pytest.raises(ConflictError, match="מאוישים"):
        service.assign(COMPLEX, kitchen["id"], TEAM, "יוסי", TUESDAY)

    weekend = service.create_type(COMPLEX, {"name": "שמירה", "days": ["שישי", "יום שבת"]})
    assert weekend["days"] == ["שישי", "שבת"]
    with pytest.raises(AgentError, match="לא מתקיימת"):
        service.assign(COMPLEX, weekend["id"], TEAM, "יוסי", TUESDAY)
    service.assign(COMPLEX, weekend["id"], TEAM, "יוסי", "2026-11-14")  # a Saturday

    service.update_type(COMPLEX, kitchen["id"], {"active": False, "seats": 2})
    with pytest.raises(AgentError, match="אינה פעילה"):
        service.assign(COMPLEX, kitchen["id"], TEAM, "יוסי", TUESDAY)


@pytest.mark.parametrize("payload, message", [
    ({"name": ""}, "שם"),
    ({"name": "x", "seats": 0}, "מספר החיילים"),
    ({"name": "x", "weight": 9}, "משקל"),
    ({"name": "x", "days": ["יום שמיני"]}, "יום לא מוכר"),
])
def test_a_duty_type_is_checked_in_hebrew(setup, payload, message):
    service = setup[0]
    with pytest.raises(AgentError, match=message):
        service.create_type(COMPLEX, payload)


def test_a_span_is_bounded(setup):
    service = setup[0]
    with pytest.raises(AgentError):
        service.duties(COMPLEX, "2026-11-01", "2027-02-01")
    with pytest.raises(AgentError):
        service.duties(COMPLEX, "2026-11-10", "2026-11-01")
    assert service.duties(COMPLEX, "2026-11-01", "2026-11-30")["duties"] == []


def test_recording_a_past_duty_counts_without_planning_rules(setup):
    service, repo, told, kitchen = setup
    service.update_type(COMPLEX, kitchen["id"], {"active": False, "days": ["שישי"]})
    repo.shifts = [_shift(TUESDAY, "ערב", "15:00", "23:00")]
    service.assign(COMPLEX, kitchen["id"], TEAM, "יוסי", TUESDAY, blocks=False)

    result = service.assign(COMPLEX, kitchen["id"], TEAM, "דנה", TUESDAY,
                            "לפני המערכת", blocks=False)

    assert result["duty"]["blocks"] is False
    assert result["conflicts"] == []  # it blocks nothing, so it collides with nothing
    assert repo.changes[-1]["action"] == ACTION_COMPLEX_DUTY_RECORDED
    assert told[-1] == (TEAM, COMPLEX, "רשם תורנות מכלול שכבר נעשתה")
    with pytest.raises(AgentError, match="לא נמצא/ת"):  # the roster is still checked
        service.assign(COMPLEX, kitchen["id"], TEAM, "אבי", TUESDAY, blocks=False)


def test_the_roster_lists_every_soldier_of_every_team(setup):
    service = setup[0]
    [team] = service.roster(COMPLEX)
    assert team["name"] == "משמרת א"
    assert [(row["name"], row["inactive_from"]) for row in team["soldiers"]] == [
        ("דנה", ""), ("יוסי", ""), ("רון", "2026-11-05")]



class _Schedules:
    """What `collisions.py` asks of the ScheduleService, recorded."""

    def __init__(self, busy=()):
        self.calls, self.busy = [], set(busy)

    def unassign(self, team_id, assignment_id, reason="", schedule_id=None):
        self.calls.append(("unassign", assignment_id, reason, current_actor()))

    def start_range_generation(self, team_id, schedule_id, starts_on, ends_on, shifts=None,
                               keep_existing=False):
        if schedule_id in self.busy:
            raise ConflictError("בנייה אחרת רצה על הסידור הזה")
        self.calls.append(("range", schedule_id, starts_on, ends_on, tuple(shifts), keep_existing))

    def queue_generation(self, team_id, schedule_id):
        self.calls.append(("queue", schedule_id))


def _with_schedules(schedules, today="2026-11-09"):
    repo, told = _Repo(), []
    service = ComplexDutyService(repo, _Complexes(), notify=lambda *args: told.append(args),
                                 schedules=schedules, today=lambda: today)
    kitchen = service.create_type(COMPLEX, {"name": "מטבח", "seats": 3})
    return service, repo, told, kitchen


def test_a_draft_shift_is_vacated_and_refilled_around_the_board():
    schedules = _Schedules()
    service, repo, told, kitchen = _with_schedules(schedules)
    repo.shifts = [_shift(MONDAY, "לילה", "23:00", "07:00"), _shift(TUESDAY, "ערב", "15:00", "23:00")]

    result = service.assign(COMPLEX, kitchen["id"], TEAM, "דנה", TUESDAY)

    assert [c["outcome"] for c in result["conflicts"]] == ["vacated", "vacated"]
    assert schedules.calls == [
        ("unassign", "a-2026-11-09-לילה", "תורנות מכלול: מטבח", "commander:" + COMPLEX),
        ("unassign", "a-2026-11-10-ערב", "תורנות מכלול: מטבח", "commander:" + COMPLEX),
        ("range", "s-1", MONDAY, TUESDAY, ("לילה", "ערב"), True),
        ("queue", "s-1"),
    ]
    assert told[-1] == (TEAM, COMPLEX, "הוריד חייל ממשמרת בגלל תורנות מכלול, והמשבצת מושלמת מחדש")


def test_a_published_week_and_the_past_are_left_and_the_team_is_told():
    schedules = _Schedules()
    service, repo, told, kitchen = _with_schedules(schedules, today=TUESDAY)
    repo.shifts = [_shift(MONDAY, "לילה", "23:00", "07:00"),
                   _shift(TUESDAY, "ערב", "15:00", "23:00", status="published", schedule="s-2")]

    result = service.assign(COMPLEX, kitchen["id"], TEAM, "דנה", TUESDAY)

    assert [c["outcome"] for c in result["conflicts"]] == ["past", "published"]
    assert schedules.calls == []
    assert "בשבוע שפורסם — יש למצוא מחליף" in told[-1][2]


def test_a_week_already_being_built_is_vacated_without_a_refill():
    schedules = _Schedules(busy={"s-1"})
    service, repo, _, kitchen = _with_schedules(schedules)
    repo.shifts = [_shift(TUESDAY, "ערב", "15:00", "23:00")]

    result = service.assign(COMPLEX, kitchen["id"], TEAM, "דנה", TUESDAY)

    assert [c["outcome"] for c in result["conflicts"]] == ["vacated_only"]
    assert [call[0] for call in schedules.calls] == ["unassign"]
