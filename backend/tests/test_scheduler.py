"""The scheduler and the change agent, against a fake model.

Both are stateless by design, so their whole contract is testable with no
database: hand them a profile and a scripted model reply, assert what comes
back. What these pin down is the part that is *not* the model's judgment —
the slot grid, which is arithmetic, and the two reason gates, which are
decisions the product cannot afford to leave to a prompt.
"""

import datetime
import json

import pytest

from app.bl.changes import ChangeAgent, OP_ASSIGN, OP_REMOVE, OP_SWAP
from app.bl.scheduler import Scheduler, build_slots
from app.common.errors import AgentError

MORNING = "בוקר"
EVENING = "צהריים"

PROFILE = {
    "workplace": {"name": "מוקד", "mission": "מענה"},
    "employees": [
        {"name": "דנה", "eligible_shifts": [MORNING]},
        {"name": "יוסי", "eligible_shifts": [MORNING, EVENING]},
        {"name": "רון", "eligible_shifts": [EVENING]},
    ],
    "shifts": [
        {
            "name": MORNING, "start_time": "07:00", "end_time": "15:00",
            "days": [], "is_on_call": False, "hour_weight": 1.0,
            "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
        },
        {
            "name": EVENING, "start_time": "15:00", "end_time": "23:00",
            "days": ["יום ראשון"], "is_on_call": False, "hour_weight": 1.0,
            "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
        },
    ],
    "rules": [{"text": "אסור שתי משמרות ברצף", "priority": "hard"}],
}


class _ScriptedLlm:
    """Returns the next scripted answer and records what it was asked."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.calls = []

    def complete_json(self, system, user, schema=None, flow=""):
        self.calls.append({"system": system, "user": user})
        if not self._answers:
            raise AssertionError("model called more times than scripted")
        return self._answers.pop(0)


# -- the slot grid ---------------------------------------------------------

def test_slots_cover_every_day_of_the_period():
    """A shift with no `days` runs every day.

    An empty list means "not restricted", not "never" -- reading it as never
    would turn a complete-looking profile into an empty schedule.
    """
    slots = build_slots(PROFILE, "2026-08-17", "2026-08-19")
    morning = [slot for slot in slots if slot["shift_name"] == MORNING]
    assert [slot["slot_date"] for slot in morning] == [
        "2026-08-17", "2026-08-18", "2026-08-19",
    ]


def test_a_shift_restricted_to_a_weekday_only_appears_on_it():
    """2026-08-23 is a Sunday; the evening shift runs only on Sundays."""
    slots = build_slots(PROFILE, "2026-08-17", "2026-08-23")
    evening = [slot for slot in slots if slot["shift_name"] == EVENING]
    assert [slot["slot_date"] for slot in evening] == ["2026-08-23"]


def test_weekdays_work_with_or_without_the_day_prefix():
    """Natural interview answers usually say ``ראשון``, not ``יום ראשון``.

    Both spellings are profile data for the same weekday. שבת previously
    appeared to work only because it is conventionally written without the
    prefix in both places.
    """
    shifts = [{
        "name": MORNING, "start_time": "07:00", "end_time": "15:00",
        "days": ["ראשון", "שני"],
        "staffing": [
            {"days": [], "headcount": 1},
            {"days": ["שני"], "headcount": 2},
        ],
    }]

    slots = build_slots({"shifts": shifts}, "2026-08-23", "2026-08-25")

    assert [(row["slot_date"], row["headcount"]) for row in slots] == [
        ("2026-08-23", 1),
        ("2026-08-24", 2),
    ]


def test_headcount_follows_the_matching_day_group():
    shifts = [{
        "name": MORNING, "start_time": "07:00", "end_time": "15:00",
        "days": [], "staffing": [
            {"days": [], "headcount": 3},
            {"days": ["יום שישי"], "headcount": 1},
        ],
    }]
    slots = build_slots({"shifts": shifts}, "2026-08-20", "2026-08-21")
    by_date = {slot["slot_date"]: slot["headcount"] for slot in slots}
    # 2026-08-20 is a Thursday, 2026-08-21 a Friday.
    assert by_date == {"2026-08-20": 3, "2026-08-21": 1}


def test_an_inverted_or_oversized_period_is_refused():
    with pytest.raises(AgentError):
        build_slots(PROFILE, "2026-08-20", "2026-08-17")
    with pytest.raises(AgentError):
        build_slots(PROFILE, "2026-01-01", "2027-12-31")


def test_generating_without_any_shift_is_an_error_not_an_empty_schedule():
    """A profile with no vocabulary cannot produce a grid, and saying so
    beats returning an empty schedule that looks like a success."""
    scheduler = Scheduler(_ScriptedLlm([]))
    with pytest.raises(AgentError):
        scheduler.generate({"shifts": []}, "2026-08-17", "2026-08-18")


# -- assignments -----------------------------------------------------------

def _reply(assignments, notes=None, summary="סידור לשבוע"):
    return {
        "assignments": assignments,
        "notes": notes or [],
        "summary": summary,
    }


def test_assignments_come_back_with_their_reasons():
    llm = _ScriptedLlm([_reply([
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-17",
         "reason": "דנה מוסמכת לבוקר ובשעות הנמוכות בצוות"},
    ])])
    result = Scheduler(llm).generate(PROFILE, "2026-08-17", "2026-08-18")
    assert len(result["assignments"]) == 1
    assert result["assignments"][0]["reason"].startswith("דנה מוסמכת")


def test_daily_generation_uses_ids_and_filters_unavailable_candidates():
    llm = _ScriptedLlm([_reply([{
        "employee_id": "employee-2",
        "slot_id": "slot-1",
        "reason": "יוסי זמין ומוסמך לבוקר",
    }])])
    result = Scheduler(llm).generate_day(
        PROFILE,
        "2026-08-17",
        availability=[{
            "employee": "דנה", "date": "2026-08-17", "shift": MORNING,
            "available": False,
        }],
        instructions="להתחשב בכללים הקשיחים",
    )

    assert result["assignments"][0]["employee"] == "יוסי"
    payload = json.loads(llm.calls[0]["user"])
    assert payload["period"]["starts_on"] == payload["period"]["ends_on"]
    assert payload["period"]["slots"][0]["candidate_employee_ids"] == [
        "employee-2"
    ]
    assert payload["instructions"] == "להתחשב בכללים הקשיחים"
    assert payload["profile"]["rules"] == PROFILE["rules"]


def test_daily_generation_repairs_a_rejected_model_row_once():
    llm = _ScriptedLlm([
        _reply([{
            "employee": "שם שלא קיים", "shift": MORNING,
            "date": "2026-08-17", "reason": "טעות",
        }]),
        _reply([{
            "employee_id": "employee-1", "slot_id": "slot-1",
            "reason": "דנה מוסמכת וזמינה לבוקר",
        }]),
    ])

    result = Scheduler(llm).generate_day(PROFILE, "2026-08-17")

    assert len(llm.calls) == 2
    assert result["assignments"][0]["employee"] == "דנה"
    assert result["metrics"]["repaired"] is True
    assert result["metrics"]["rejected"] == 1
    repair = json.loads(llm.calls[1]["user"])["repair"]
    assert repair["rejected_rows"]


def test_next_daily_call_sees_yesterday_and_cumulative_fairness():
    yesterday = [{
        "employee": "דנה", "shift": MORNING, "date": "2026-08-17",
        "reason": "כיסוי",
    }]
    llm = _ScriptedLlm([_reply([{
        "employee_id": "employee-2", "slot_id": "slot-1",
        "reason": "יוסי מאזן את העומס",
    }])])

    Scheduler(llm).generate_day(
        PROFILE, "2026-08-18", already_scheduled=yesterday
    )

    payload = json.loads(llm.calls[0]["user"])
    assert payload["already_scheduled"][0]["employee"] == "דנה"
    fairness = {row["employee"]: row for row in payload["fairness"]}
    assert fairness["דנה"]["shifts"] == 1


def test_manager_required_assignment_is_kept_when_model_omits_it():
    llm = _ScriptedLlm([_reply([])])
    result = Scheduler(llm).generate(
        PROFILE,
        "2026-08-17",
        "2026-08-18",
        required_assignments=[{
            "employee": "דנה", "shift": MORNING, "date": "2026-08-17",
        }],
    )

    assert result["assignments"] == [{
        "employee": "דנה",
        "shift": MORNING,
        "date": "2026-08-17",
        "reason": "שיבוץ חובה שנבחר על ידי המנהל בעת בניית הסידור",
    }]
    payload = json.loads(llm.calls[0]["user"])
    assert payload["required_assignments"] == [{
        "employee": "דנה", "shift": MORNING, "date": "2026-08-17",
    }]


def test_required_assignment_must_name_a_real_slot_and_employee():
    with pytest.raises(AgentError):
        Scheduler(_ScriptedLlm([])).generate(
            PROFILE,
            "2026-08-17",
            "2026-08-18",
            required_assignments=[{
                "employee": "לא קיים", "shift": MORNING,
                "date": "2026-08-17",
            }],
        )


def test_an_assignment_without_a_reason_is_dropped():
    """D8 enforced in code, not left to the prompt.

    An assignment nobody can account for is dropped rather than stored --
    storing it is how the decision gets quietly lost, at exactly the moment
    the manager would have caught a bad call cheaply.
    """
    llm = _ScriptedLlm([_reply([
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-17",
         "reason": ""},
        {"employee": "יוסי", "shift": MORNING, "date": "2026-08-18",
         "reason": "יוסי זמין"},
    ])])
    result = Scheduler(llm).generate(PROFILE, "2026-08-17", "2026-08-18")
    assert [row["employee"] for row in result["assignments"]] == ["יוסי"]


def test_an_assignment_to_a_slot_outside_the_period_is_dropped():
    llm = _ScriptedLlm([_reply([
        {"employee": "דנה", "shift": MORNING, "date": "2026-09-01",
         "reason": "מחוץ לתקופה"},
    ])])
    result = Scheduler(llm).generate(PROFILE, "2026-08-17", "2026-08-18")
    assert result["assignments"] == []


def test_an_unknown_employee_is_dropped():
    """A name nobody declared cannot be rostered onto a real shift."""
    llm = _ScriptedLlm([_reply([
        {"employee": "מישהו אחר", "shift": MORNING, "date": "2026-08-17",
         "reason": "המצאה"},
    ])])
    result = Scheduler(llm).generate(PROFILE, "2026-08-17", "2026-08-18")
    assert result["assignments"] == []


def test_a_questionable_but_valid_assignment_is_kept():
    """The scheduler is not a second audit.

    Assigning someone outside `eligible_shifts` is a bad call the audit will
    comment on. Dropping it here would make this code the authority D3 says
    it is not -- the agent decides, and code reports.
    """
    llm = _ScriptedLlm([_reply([
        {"employee": "רון", "shift": MORNING, "date": "2026-08-17",
         "reason": "אין אף אחד אחר זמין"},
    ])])
    result = Scheduler(llm).generate(PROFILE, "2026-08-17", "2026-08-18")
    assert len(result["assignments"]) == 1


def test_duplicate_assignments_are_collapsed():
    row = {"employee": "דנה", "shift": MORNING, "date": "2026-08-17",
           "reason": "זמינה"}
    llm = _ScriptedLlm([_reply([row, dict(row)])])
    result = Scheduler(llm).generate(PROFILE, "2026-08-17", "2026-08-18")
    assert len(result["assignments"]) == 1


def test_notes_survive_to_the_caller():
    """`notes` is where a slot left short gets said out loud."""
    llm = _ScriptedLlm([_reply([], notes=["לא היה מי לאייש את בוקר שישי"])])
    result = Scheduler(llm).generate(PROFILE, "2026-08-17", "2026-08-18")
    assert result["notes"] == ["לא היה מי לאייש את בוקר שישי"]


def test_the_model_is_handed_the_rules_as_written():
    """Rules travel as the manager's sentences, unparsed (D2)."""
    llm = _ScriptedLlm([_reply([])])
    Scheduler(llm).generate(PROFILE, "2026-08-17", "2026-08-18")
    assert "אסור שתי משמרות ברצף" in llm.calls[0]["user"]


# -- the change agent ------------------------------------------------------

SCHEDULE = {
    "id": "sched-1",
    "starts_on": "2026-08-17",
    "ends_on": "2026-08-23",
    "slots": [
        {"shift_name": MORNING, "slot_date": "2026-08-20", "headcount": 1},
        {"shift_name": MORNING, "slot_date": "2026-08-21", "headcount": 1},
    ],
    "assignments": [
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-20",
         "reason": "שיבוץ מקורי"},
    ],
}


def _change(operations=None, needs_reason=False, agent_reason="",
            constraints=None, reply="הצעה"):
    return {
        "reply": reply,
        "needs_reason": needs_reason,
        "agent_reason": agent_reason,
        "operations": operations or [],
        "constraints": constraints or [],
    }


def test_a_request_without_a_reason_asks_for_one_and_proposes_nothing():
    """D8: the answer to a missing reason is a question, not a rejection."""
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_REMOVE, "employee": "דנה",
                     "shift": MORNING, "date": "2026-08-20", "reason": ""}],
        needs_reason=True, reply="למה דנה לא מגיעה?",
    )])
    proposal = ChangeAgent(llm).propose(PROFILE, SCHEDULE, "תוריד את דנה")
    assert proposal["needs_reason"] is True
    assert proposal["operations"] == []


def test_a_stated_reason_lets_the_proposal_through():
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_ASSIGN, "employee": "יוסי",
                     "shift": MORNING, "date": "2026-08-20",
                     "reason": "יוסי ב-22 שעות מול רון ב-31"}],
        agent_reason="יוסי הכי פנוי ומוסמך לבוקר",
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "דנה לא מגיעה", stated_reason="מחלה",
    )
    assert proposal["needs_reason"] is False
    assert proposal["stated_reason"] == "מחלה"
    assert proposal["agent_reason"]


def test_operations_are_withdrawn_when_the_model_forgets_to_justify():
    """A change with neither reason cannot land in the append-only log.

    Enforced here rather than trusted to the prompt: a model that forgets
    once would otherwise write an unexplained row into the only history the
    system keeps.
    """
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_REMOVE, "employee": "דנה",
                     "shift": MORNING, "date": "2026-08-20", "reason": ""}],
        agent_reason="",
    )])
    proposal = ChangeAgent(llm).propose(PROFILE, SCHEDULE, "תוריד את דנה")
    assert proposal["needs_reason"] is True
    assert proposal["operations"] == []


def test_an_operation_on_a_slot_the_period_lacks_is_dropped():
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_ASSIGN, "employee": "יוסי",
                     "shift": MORNING, "date": "2026-12-25",
                     "reason": "מחוץ לתקופה"}],
        agent_reason="נימוק",
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "שבץ את יוסי", stated_reason="כיסוי",
    )
    assert proposal["operations"] == []


def test_a_swap_needs_both_halves_to_exist():
    llm = _ScriptedLlm([_change(
        operations=[{
            "action": OP_SWAP, "employee": "דנה", "shift": MORNING,
            "date": "2026-08-20", "with_employee": "יוסי",
            "with_shift": MORNING, "with_date": "2026-08-21",
            "reason": "החלפה",
        }],
        agent_reason="שניהם מוסמכים",
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "תחליף ביניהם", stated_reason="בקשת העובדים",
    )
    assert len(proposal["operations"]) == 1
    assert proposal["operations"][0]["with_employee"] == "יוסי"


def test_an_implied_constraint_is_captured_for_next_time():
    """"דנה חולה ביום חמישי" is both a change and a fact about Thursday.

    Storing the fact is what stops the next schedule putting her right back.
    """
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_REMOVE, "employee": "דנה",
                     "shift": MORNING, "date": "2026-08-20",
                     "reason": "חולה"}],
        agent_reason="דנה לא זמינה",
        constraints=[{"employee": "דנה", "date": "2026-08-20",
                      "shift": "", "reason": "מחלה"}],
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "דנה חולה ביום חמישי", stated_reason="מחלה",
    )
    assert proposal["constraints"][0]["employee"] == "דנה"


def test_an_empty_request_is_refused():
    with pytest.raises(AgentError):
        ChangeAgent(_ScriptedLlm([])).propose(PROFILE, SCHEDULE, "   ")


def test_the_proposal_never_applies_anything():
    """Propose and apply are two calls; this one writes nothing.

    Asserted structurally: the agent is handed no repository at all, so
    there is nothing it could write to even if it tried.
    """
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_REMOVE, "employee": "דנה",
                     "shift": MORNING, "date": "2026-08-20",
                     "reason": "חולה"}],
        agent_reason="נימוק",
    )])
    before = [dict(row) for row in SCHEDULE["assignments"]]
    ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "דנה חולה", stated_reason="מחלה",
    )
    assert SCHEDULE["assignments"] == before


def test_change_context_serializes_database_dates_and_timestamps():
    llm = _ScriptedLlm([_change()])
    ChangeAgent(llm).propose(
        PROFILE,
        SCHEDULE,
        "מה כדאי לשנות?",
        availability=[{
            "constraint_date": datetime.date(2026, 8, 20),
            "created_at": datetime.datetime(2026, 8, 18, 9, 30),
        }],
        history=[{
            "slot_date": datetime.date(2026, 8, 19),
            "created_at": datetime.datetime(
                2026, 8, 18, 10, 0, tzinfo=datetime.timezone.utc,
            ),
        }],
    )

    payload = json.loads(llm.calls[0]["user"])
    assert payload["availability"][0]["constraint_date"] == "2026-08-20"
    assert payload["availability"][0]["created_at"] == "2026-08-18T09:30:00"
    assert payload["history"][0]["created_at"] == "2026-08-18T10:00:00+00:00"


# -- chunking: model output stays small enough to cover the whole period ---

def _week_profile():
    """A one-shift workplace, so the slot count tracks the day count."""
    return {
        "workplace": {"name": "מוקד"},
        "employees": [{"name": "דנה"}, {"name": "יוסי"}, {"name": "רון"}],
        "shifts": [{
            "name": MORNING, "start_time": "07:00", "end_time": "15:00",
            "days": [], "is_on_call": False,
            "staffing": [{"days": [], "headcount": 1}],
        }],
        "rules": [],
    }


def _covering(first, last, employee="דנה"):
    return _reply([
        {"employee": employee, "shift": MORNING,
         "date": "2026-08-%02d" % day, "reason": "כיסוי"}
        for day in range(first, last + 1)
    ])


def test_a_short_period_is_still_one_call():
    """The common case must not pay for the long one: a single week is built
    in exactly one model call, as it always was."""
    llm = _ScriptedLlm([_covering(17, 23)])
    Scheduler(llm).generate(_week_profile(), "2026-08-17", "2026-08-23")
    assert len(llm.calls) == 1


def test_a_busy_week_is_split_by_staffing_volume_not_just_days():
    profile = _week_profile()
    profile["shifts"] = [
        dict(
            profile["shifts"][0],
            name=name,
            staffing=[{"days": [], "headcount": 2}],
        )
        for name in (MORNING, EVENING, "לילה")
    ]
    required = [
        {"employee": "דנה", "shift": shift, "date": date}
        for date, shift in (
            ("2026-08-17", MORNING),
            ("2026-08-19", EVENING),
            ("2026-08-23", "לילה"),
        )
    ]
    llm = _ScriptedLlm([_reply([]) for _ in range(4)])

    result = Scheduler(llm).generate(
        profile,
        "2026-08-17",
        "2026-08-23",
        required_assignments=required,
    )

    assert len(llm.calls) == 4
    assert [
        {key: row[key] for key in ("employee", "shift", "date")}
        for row in result["assignments"]
    ] == required
    for call in llm.calls:
        payload = json.loads(call["user"])
        assert sum(
            slot["headcount"] for slot in payload["period"]["slots"]
        ) <= 14


def test_a_long_period_is_split_into_weeks():
    llm = _ScriptedLlm([_covering(17, 23), _covering(24, 30)])
    result = Scheduler(llm).generate(
        _week_profile(), "2026-08-17", "2026-08-30"
    )
    assert len(llm.calls) == 2
    assert len(result["assignments"]) == 14


def test_a_chunk_never_splits_a_day_across_two_calls():
    """Half a Tuesday in one request and half in another is how one person
    ends up on two shifts at once, with neither call able to notice."""
    profile = _week_profile()
    profile["shifts"].append({
        "name": EVENING, "start_time": "15:00", "end_time": "23:00",
        "days": [], "is_on_call": False,
        "staffing": [{"days": [], "headcount": 1}],
    })
    llm = _ScriptedLlm([_reply([]), _reply([])])
    Scheduler(llm).generate(profile, "2026-08-17", "2026-08-30")
    for call in llm.calls:
        payload = json.loads(call["user"])
        dates = [slot["date"] for slot in payload["period"]["slots"]]
        # Every date present appears once per shift, never split.
        assert all(dates.count(date) == 2 for date in set(dates))


def test_a_later_chunk_is_told_what_the_earlier_one_decided():
    """A scheduler that cannot see week one gives week two to the same
    people -- turning the fairness feature into the unfairness it prevents."""
    llm = _ScriptedLlm([_covering(17, 23), _covering(24, 30, "יוסי")])
    Scheduler(llm).generate(_week_profile(), "2026-08-17", "2026-08-30")
    second = json.loads(llm.calls[1]["user"])
    assert len(second["already_scheduled"]) == 7
    assert second["already_scheduled"][0]["employee"] == "דנה"
    # Without the reasons: the next chunk needs to know a slot is taken, not
    # to re-read a paragraph of justification per row.
    assert "reason" not in second["already_scheduled"][0]


def test_the_fairness_tally_grows_with_what_this_run_has_placed():
    """Week two must see week one's shifts as shifts already worked."""
    llm = _ScriptedLlm([_covering(17, 23), _covering(24, 30, "יוסי")])
    Scheduler(llm).generate(_week_profile(), "2026-08-17", "2026-08-30")
    first = json.loads(llm.calls[0]["user"])
    second = json.loads(llm.calls[1]["user"])
    before = {row["employee"]: row for row in first["fairness"]}
    after = {row["employee"]: row for row in second["fairness"]}
    assert before["דנה"]["shifts"] == 0
    assert after["דנה"]["shifts"] == 7


def test_an_assignment_repeated_by_a_later_chunk_is_not_duplicated():
    """The later call is the one working from incomplete information, so the
    earlier decision stands."""
    llm = _ScriptedLlm([_covering(17, 23), _covering(17, 23)])
    result = Scheduler(llm).generate(
        _week_profile(), "2026-08-17", "2026-08-30"
    )
    assert len(result["assignments"]) == 7


def test_notes_from_every_chunk_survive():
    """A slot left short in week one is not the manager's problem only until
    week two is built."""
    llm = _ScriptedLlm([
        _reply([], notes=["חסר אדם ביום שני"]),
        _reply([], notes=["חסר אדם ביום שלישי"]),
    ])
    result = Scheduler(llm).generate(
        _week_profile(), "2026-08-17", "2026-08-30"
    )
    assert result["notes"] == ["חסר אדם ביום שני", "חסר אדם ביום שלישי"]


def test_the_slot_grid_is_the_whole_period_not_the_last_chunk():
    llm = _ScriptedLlm([_reply([]), _reply([])])
    result = Scheduler(llm).generate(
        _week_profile(), "2026-08-17", "2026-08-30"
    )
    assert len(result["slots"]) == 14
