"""The scheduler and the change agent, against a fake model.

Both are stateless by design, so their whole contract is testable with no
database. The scheduler's model only translates sentences (D34); the slot
grid and the assignment are code, and so are the change agent's two
reason gates.
"""

import datetime
import json

import pytest

from app.bl.changes import ChangeAgent, OP_ASSIGN, OP_REMOVE, OP_SWAP
from app.bl.scheduler import Scheduler, build_slots, effective_availability
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
        self.calls.append({"system": system, "user": user, "schema": schema})
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


# -- assignments -----------------------------------------------------------


PLAIN = dict(PROFILE, rules=[])


def _translation(requests=(), unresolved=()):
    return {"calls": [], "directives": [], "requests": list(requests),
            "unresolved": list(unresolved),
            "timing": [{"source_id": "source-1", "kind": "none", "phrase": "", "starts_on": "",
                        "ends_on": "", "maybe_through": "", "question": ""}]}


def test_structured_input_is_solved_with_no_model_call():
    llm = _ScriptedLlm([])

    result = Scheduler(llm).generate_span(PLAIN, "2026-08-30", "2026-09-05")

    assert llm.calls == []
    assert result["metrics"]["engine"] == "solver"
    assert result["metrics"]["total_tokens"] == 0
    assert len(result["assignments"]) == 8
    assert all(row["reason"] for row in result["assignments"])


def test_an_instruction_is_translated_and_the_solver_honours_it():
    avoid = {"kind": "avoid", "employees": ["יוסי"], "shifts": [MORNING], "is_hard": True,
             "reason": "יוסי לא בבקרים השבוע", "source_id": "source-1"}
    llm = _ScriptedLlm([_translation([avoid])])

    result = Scheduler(llm).generate_span(PLAIN, "2026-08-30", "2026-09-05",
                                          instructions="יוסי לא בבקרים השבוע")

    assert len(llm.calls) == 1
    assert result["metrics"]["engine"] == "hybrid"
    assert not [row for row in result["assignments"]
                if row["employee"] == "יוסי" and row["shift"] == MORNING]


def test_a_binding_sentence_that_did_not_translate_is_reported_not_dropped():
    left = {"source_id": "source-1", "reason": "לא ברור על מי מדובר"}
    llm = _ScriptedLlm([_translation(unresolved=[left])])

    result = Scheduler(llm).generate_span(PLAIN, "2026-08-30", "2026-08-30",
                                          instructions="שהחדש לא יהיה לבד")

    assert result["assignments"]
    assert "לא נאכפה" in result["notes"][0] and "שהחדש לא יהיה לבד" in result["notes"][0]


def test_an_unreachable_model_still_builds_and_names_what_it_skipped():
    class _Down:
        def complete_json(self, *args, **kwargs):
            raise AgentError("אין חיבור")

    result = Scheduler(_Down()).generate_span(PROFILE, "2026-08-30", "2026-08-30")

    assert result["assignments"]
    assert "אסור שתי משמרות ברצף" in result["notes"][0]


def test_rows_to_keep_are_kept_where_they_still_fit():
    keep = [{"employee": "יוסי", "shift": MORNING, "date": "2026-08-31"}]

    result = Scheduler(None).generate_span(PLAIN, "2026-08-31", "2026-08-31", keep=keep)

    assert [row["employee"] for row in result["assignments"]] == ["יוסי"]


def test_a_period_with_no_shift_is_an_error_not_an_empty_schedule():
    with pytest.raises(AgentError):
        Scheduler(None).generate_verified(dict(PLAIN, shifts=[]), "2026-08-30", "2026-09-05")



def test_rotation_b_is_the_slot_complement_of_rotation_a():
    profile = dict(
        PROFILE,
        workplace={
            "name": "מוקד", "rotation_mode": "round",
            "rotation_a_unavailability": [{
                "days": ["שני"], "shifts": [MORNING],
                "start_time": "", "end_time": "", "reason": "יציאה",
            }],
        },
        employees=[
            dict(PROFILE["employees"][0], exit_pattern="round", rotation_group="א"),
            dict(PROFILE["employees"][1], exit_pattern="round", rotation_group="ב"),
        ],
    )

    rows = effective_availability(
        profile, [], "2026-08-17", "2026-08-18"
    )

    assert [(row["employee"], row["date"], row["shift"])
            for row in rows] == [
        ("דנה", "2026-08-17", MORNING),
        ("יוסי", "2026-08-18", MORNING),
    ]
    assert all(row["source"] == "rotation" and row["is_hard"] for row in rows)


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
