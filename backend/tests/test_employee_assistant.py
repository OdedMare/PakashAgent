"""The employee's assistant: clean swaps in code, phrasing by the model (D27).

What a reviewer would otherwise take on trust:

- **every suggested swap was checked** -- one that puts a colleague on a day
  they are unavailable, or the employee on two shifts at once, never appears;
- **the model can only pick by id** -- an invented id is dropped, so the model
  cannot slip in a swap the audit never saw;
- **colleagues' constraints never reach the model** -- not the row, not the
  reason;
- **no model, no problem** -- a failure answers from the same clean list.
"""

import datetime
import json

from app.bl.employee_service.assistant import EmployeeAssistant
from app.bl.employee_service.swap_options import swap_options
from app.common.errors.errors import AgentError
from app.common.time_context.time_context import israel_today

MORNING = "בוקר"
EVENING = "ערב"
DANA = "דנה"
YOSSI = "יוסי"
RON = "רון"
SECRET_REASON = "טיפול רפואי פרטי"

PROFILE = {
    "employees": [{"name": DANA}, {"name": YOSSI}, {"name": RON}],
    "shifts": [
        {"name": MORNING, "start_time": "07:00", "end_time": "15:00",
         "is_on_call": False, "hour_weight": 1.0,
         "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
        {"name": EVENING, "start_time": "15:00", "end_time": "23:00",
         "is_on_call": False, "hour_weight": 1.0,
         "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
    ],
    "rules": [],
}

TODAY = israel_today()
D1, D2, D3 = ((TODAY + datetime.timedelta(days=n)).isoformat() for n in (2, 3, 4))


def _schedule():
    rows = [
        ("a1", DANA, MORNING, D1), ("a2", YOSSI, EVENING, D1),
        ("a3", YOSSI, MORNING, D2), ("a4", RON, EVENING, D2),
        ("a5", DANA, MORNING, D3), ("a6", RON, EVENING, D3),
    ]
    slots = [
        {"shift_name": shift, "slot_date": date, "headcount": 1,
         "start_time": "07:00" if shift == MORNING else "15:00",
         "end_time": "15:00" if shift == MORNING else "23:00"}
        for date in (D1, D2, D3) for shift in (MORNING, EVENING)
    ]
    return {
        "id": "sched-1", "starts_on": D1, "ends_on": D3, "status": "published",
        "slots": slots, "warnings": [],
        "assignments": [
            {"id": row_id, "employee": name, "shift": shift, "date": date, "reason": "x"}
            for row_id, name, shift, date in rows
        ],
    }


# Yossi cannot work on D3, for a reason only the manager should read.
AVAILABILITY = [{
    "employee": YOSSI, "constraint_date": D3, "shift_name": "",
    "available": False, "reason": SECRET_REASON, "source": "manager",
}]


def _options():
    return swap_options(_schedule(), PROFILE, AVAILABILITY, DANA, TODAY)


def test_every_option_trades_one_of_my_shifts_with_a_colleague():
    options = _options()

    assert options
    mine = {"a1", "a5"}
    for option in options:
        assert option["mine"]["assignment_id"] in mine
        assert option["colleague"] in (YOSSI, RON)
        assert option["theirs"]["assignment_id"] not in mine
    assert len({option["id"] for option in options}) == len(options)


def test_a_swap_onto_a_colleagues_unavailable_day_is_never_offered():
    """Yossi taking Dana's D3 morning would contradict his constraint."""
    for option in _options():
        if option["colleague"] == YOSSI:
            assert option["mine"]["date"] != D3


def test_a_swap_that_double_books_me_is_never_offered():
    """Ron's D3 evening for Dana's D1 morning leaves Dana on D3 twice."""
    for option in _options():
        if option["theirs"]["date"] == D3:
            assert option["mine"]["date"] == D3


def test_past_shifts_are_not_traded():
    later = TODAY + datetime.timedelta(days=3)  # D1 and D2 are now past
    options = swap_options(_schedule(), PROFILE, AVAILABILITY, DANA, later)

    assert all(option["mine"]["date"] >= later.isoformat() for option in options)
    assert all(option["theirs"]["date"] >= later.isoformat() for option in options)


class _Repository:
    def team_profile(self, team_id):
        return PROFILE

    def availability(self, team_id, starts_on=None, ends_on=None, employee=None):
        return [dict(row) for row in AVAILABILITY]


class _Schedules:
    def __init__(self, schedule):
        self.schedule = schedule
        self.roles = []

    def current(self, team_id, role="boss"):
        self.roles.append(role)
        return self.schedule


class _Model:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.seen = reply, error, []

    def complete_json(self, system, user, schema=None, flow="", **kwargs):
        self.seen.append(user)
        if self.error:
            raise self.error
        return self.reply


def _assistant(model=None, schedule="default"):
    schedules = _Schedules(_schedule() if schedule == "default" else schedule)
    return EmployeeAssistant(_Repository(), schedules, model), schedules


def test_the_model_picks_only_from_checked_options():
    first = _options()[0]["id"]
    model = _Model({"answer": "אפשר להחליף", "suggestions": [first, "o999", first]})
    assistant, schedules = _assistant(model)

    reply = assistant.ask("team", DANA, "עם מי אפשר להחליף?")

    assert reply["used_model"] is True
    assert [row["id"] for row in reply["suggestions"]] == [first]
    assert schedules.roles == ["member"]  # the published schedule only


def test_a_colleagues_constraint_never_reaches_the_model():
    model = _Model({"answer": "בסדר", "suggestions": []})
    assistant, _ = _assistant(model)

    assistant.ask("team", DANA, "איך לשפר את השבוע שלי?")

    payload = json.loads(model.seen[0])
    assert SECRET_REASON not in model.seen[0]
    assert "availability" not in payload
    assert "people" not in json.dumps(payload)  # no per-colleague hours


def test_a_model_failure_answers_from_the_same_clean_list():
    assistant, _ = _assistant(_Model(error=AgentError("down")))

    reply = assistant.ask("team", DANA, "עם מי אפשר להחליף?")

    assert reply["used_model"] is False
    assert reply["suggestions"]
    clean = {row["id"] for row in _options()}
    assert {row["id"] for row in reply["suggestions"]} <= clean


def test_without_a_model_configured_it_still_answers():
    assistant, _ = _assistant(None)

    reply = assistant.ask("team", DANA, "החלפה")

    assert reply["used_model"] is False
    assert reply["answer"]


def test_no_published_schedule_says_so_without_a_model_call():
    model = _Model({"answer": "x", "suggestions": []})
    assistant, _ = _assistant(model, schedule=None)

    reply = assistant.ask("team", DANA, "עם מי להחליף?")

    assert reply["suggestions"] == []
    assert model.seen == []
