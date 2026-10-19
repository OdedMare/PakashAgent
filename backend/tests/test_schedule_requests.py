"""Structured requests in the code engine: hard ones block, soft ones cost."""

import pytest

from app.bl.deterministic_scheduler import generate_span, unsupported_reason
from app.bl.scheduler.directives import read_translation, semantic_sources
from app.bl.scheduler.scheduler import Scheduler
from app.bl.shared.schedule_requests import read_requests
from app.common.errors import AgentError


MORNING, NIGHT = "בוקר", "לילה"
SUNDAY = "2026-08-16"


def _profile(people=("דנה", "יוסי", "רון"), headcount=1):
    return {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": name} for name in people],
        "shifts": [{
            "name": MORNING, "start_time": "07:00", "end_time": "15:00", "days": [],
            "staffing": [{"days": [], "headcount": headcount, "required_roles": []}],
        }],
    }


def _who(result, day=None):
    return [row["employee"] for row in result["assignments"]
            if day is None or row["date"] == day]


def test_hard_avoid_removes_the_person_from_matching_shifts():
    requests = [{"kind": "avoid", "employees": ["דנה"], "shifts": [MORNING], "is_hard": True}]

    result = generate_span(_profile(), SUNDAY, "2026-08-21", requests=requests)

    assert "דנה" not in _who(result)


def test_soft_avoid_gives_way_when_nobody_else_can_work_and_says_so():
    requests = [{"kind": "avoid", "employees": ["דנה"], "reason": "דנה ביקשה חופש"}]

    result = generate_span(_profile(people=("דנה",)), SUNDAY, SUNDAY, requests=requests)

    assert _who(result) == ["דנה"]
    assert any("דנה ביקשה חופש" in note for note in result["notes"])


def test_soft_avoid_moves_the_shift_to_someone_else_when_possible():
    requests = [{"kind": "avoid", "employees": ["דנה"], "dates": [SUNDAY]}]

    result = generate_span(_profile(people=("דנה", "יוסי")), SUNDAY, SUNDAY, requests=requests)

    assert _who(result) == ["יוסי"]


def test_prefer_outweighs_load_and_is_named_in_the_reason():
    # Without the request, Sunday goes to דנה: everyone is at zero and
    # the name breaks the tie.
    requests = [{"kind": "prefer", "employees": ["רון"], "weekdays": ["ראשון"],
                 "reason": "רון מעדיף ראשון"}]

    result = generate_span(_profile(), SUNDAY, "2026-08-18", requests=requests)

    sunday = [row for row in result["assignments"] if row["date"] == SUNDAY]
    assert [row["employee"] for row in sunday] == ["רון"]
    assert "רון מעדיף ראשון" in sunday[0]["reason"]


def test_hard_max_count_per_week_caps_the_person():
    requests = [{"kind": "max_count", "employees": ["דנה"], "count": 1,
                 "per": "week", "is_hard": True}]
    profile = _profile(people=("דנה", "יוסי", "רון", "גיל"), headcount=2)

    result = generate_span(profile, SUNDAY, "2026-08-22", requests=requests)

    assert _who(result).count("דנה") == 1


def test_hard_not_together_never_shares_a_shift():
    # Without the request, גיל and דנה share every other day.
    requests = [{"kind": "not_together", "employees": ["גיל", "דנה"], "is_hard": True}]
    profile = _profile(people=("דנה", "יוסי", "רון", "גיל"), headcount=2)

    result = generate_span(profile, SUNDAY, "2026-08-22", requests=requests)

    for day in {row["date"] for row in result["assignments"]}:
        assert not {"גיל", "דנה"} <= set(_who(result, day))
    assert len(result["assignments"]) == 14


def test_soft_availability_is_weighed_in_code_instead_of_sent_to_ai():
    availability = [{"employee": "דנה", "date": SUNDAY, "shift": MORNING,
                     "available": False, "is_hard": False}]

    assert unsupported_reason(_profile(), availability) == ""
    assert semantic_sources(_profile(), availability) == []
    result = generate_span(_profile(people=("דנה", "יוסי")), SUNDAY, SUNDAY,
                           availability=availability)
    assert _who(result) == ["יוסי"]


@pytest.mark.parametrize("request_row, message", [
    ({"kind": "avoid", "employees": ["נעמה"]}, "לא מוכר"),
    ({"kind": "prefer", "employees": ["דנה"], "is_hard": True}, "רכה"),
    ({"kind": "max_count", "employees": ["דנה"]}, "מספר שלם"),
    ({"kind": "not_together", "employees": ["דנה"]}, "שני עובדים"),
    ({"kind": "avoid", "employees": ["דנה"], "shifts": [NIGHT]}, "משמרת לא מוכרת"),
    ({"kind": "avoid", "employees": ["דנה"], "weekdays": ["יומולדת"]}, "יום בשבוע"),
    ({"kind": "swap", "employees": ["דנה"]}, "סוג בקשה"),
])
def test_invalid_requests_are_refused_with_the_reason(request_row, message):
    _, errors = read_requests([request_row], _profile())
    assert errors and message in errors[0]
    with pytest.raises(AgentError, match=message):
        generate_span(_profile(), SUNDAY, SUNDAY, requests=[request_row])


def _translated_request(**overrides):
    row = {
        "source_id": "source-1", "kind": "avoid", "employees": ["דנה"],
        "shifts": [MORNING], "dates": [], "weekdays": [], "count": None,
        "per": "period", "is_hard": False, "weight": 1, "reason": "עדיף שדנה לא בבוקר",
    }
    row.update(overrides)
    return row


def test_translation_accepts_requests_and_counts_their_sources_as_covered():
    sources = [{"id": "source-1", "kind": "instructions", "context": "", "text": "..."}]
    answer = {"directives": [], "requests": [_translated_request()], "unresolved": []}

    translated = read_translation(answer, sources, _profile(), SUNDAY, SUNDAY)

    assert translated["requests"][0]["kind"] == "avoid"
    assert translated["availability"] == []


def test_translation_with_an_invalid_request_is_refused_whole():
    sources = [{"id": "source-1", "kind": "instructions", "context": "", "text": "..."}]
    answer = {"directives": [], "requests": [_translated_request(employees=["נעמה"])],
              "unresolved": []}

    assert read_translation(answer, sources, _profile(), SUNDAY, SUNDAY) is None


class _ScriptedLlm:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def complete_json(self, system, user, schema=None, **kwargs):
        self.calls.append({"schema": schema})
        return self.answers.pop(0)


def test_auto_translates_a_soft_wish_and_code_honours_it():
    llm = _ScriptedLlm([{"directives": [], "requests": [_translated_request()],
                         "unresolved": []}])

    result = Scheduler(llm).generate_span(
        _profile(people=("דנה", "יוסי")), SUNDAY, SUNDAY,
        instructions="עדיף שדנה לא תעבוד בבוקר", engine="auto",
    )

    assert _who(result) == ["יוסי"]
    assert result["metrics"]["engine"] == "hybrid"
    assert len(llm.calls) == 1
