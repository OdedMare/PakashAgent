"""Asking instead of guessing, on both halves of the agent.

The rule is one sentence — *when carrying out a request would mean guessing
which person, shift or date it refers to, ask* — and it is worth testing
separately from either agent because it is the same rule in two places with
two different thresholds:

- **Reading** (the manager chat's questions) may interpret. A question answered against a
  reasonable reading of an unclear sentence costs a re-ask; nothing moves.
- **Writing** (`bl/changes.py`) may not. A change applied to the wrong
  person's shift has to be *found* before it can be undone, so the gate there
  is enforced in code rather than trusted to the prompt — the same treatment
  `needs_reason` already gets, and for the same reason.

What is asserted throughout is the *absence of operations*, not the wording
of the question. The question is the model's to phrase; that nothing is
queued behind it is the product's guarantee.
"""

import json


from app.bl.changes import ChangeAgent, OP_ASSIGN, OP_REMOVE, OP_SWAP
from app.bl.tools import resolve_employee

MORNING = "בוקר"
EVENING = "צהריים"
NIGHT = "לילה"

# Two people share a first name, which is the whole point of this fixture:
# "דניאל" is a real thing a manager says and it names two employees here.
DANIEL_C = "דניאל כהן"
DANIEL_L = "דניאל לוי"
MOSHE = "משה"
DANA = "דנה"

PROFILE = {
    "workplace": {"name": "מוקד"},
    "employees": [
        {"name": DANIEL_C, "role": "מוקדן", "eligible_shifts": [MORNING, EVENING]},
        {"name": DANIEL_L, "role": "מוקדן", "eligible_shifts": [MORNING, EVENING]},
        {"name": MOSHE, "role": "מוקדן", "eligible_shifts": [MORNING, EVENING]},
        {"name": DANA, "role": "מוקדנית", "eligible_shifts": [MORNING]},
    ],
    "shifts": [
        {"name": MORNING, "start_time": "07:00", "end_time": "15:00",
         "days": [], "is_on_call": False, "hour_weight": 1.0,
         "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
        {"name": EVENING, "start_time": "15:00", "end_time": "23:00",
         "days": [], "is_on_call": False, "hour_weight": 1.0,
         "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
    ],
    "rules": [],
}

SCHEDULE = {
    "id": "sched-1",
    "starts_on": "2026-08-17",
    "ends_on": "2026-08-23",
    "slots": [
        {"shift_name": MORNING, "slot_date": "2026-08-20", "headcount": 1},
        {"shift_name": EVENING, "slot_date": "2026-08-20", "headcount": 1},
        {"shift_name": MORNING, "slot_date": "2026-08-21", "headcount": 1},
    ],
    "assignments": [
        {"employee": DANA, "shift": MORNING, "date": "2026-08-20",
         "reason": "שיבוץ מקורי"},
    ],
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


def _change(operations=None, needs_reason=False, needs_input=False,
            agent_reason="", constraints=None, reply="הצעה",
            profile_operations=None):
    return {
        "reply": reply,
        "needs_reason": needs_reason,
        "needs_input": needs_input,
        "agent_reason": agent_reason,
        "operations": operations or [],
        "constraints": constraints or [],
        "profile_operations": profile_operations or [],
    }


# -- resolving a name ------------------------------------------------------

def test_a_name_matching_one_person_resolves():
    found = resolve_employee(PROFILE, MOSHE)
    assert found["found"] is True
    assert found["ambiguous"] is False


def test_a_name_matching_several_people_is_ambiguous_not_the_first():
    """The specific guess this whole change exists to refuse.

    Returning `DANIEL_C` here would be defensible, deterministic, and wrong:
    the manager named something two people answer to, and picking the one
    listed first is a coin flip dressed as a lookup.
    """
    found = resolve_employee(PROFILE, "דניאל")
    assert found["found"] is False
    assert found["ambiguous"] is True
    assert sorted(found["matches"]) == sorted([DANIEL_C, DANIEL_L])


def test_an_exact_match_wins_over_being_a_prefix_of_others():
    """A name that exists is never ambiguous, whatever else it prefixes."""
    profile = {"employees": [{"name": "דן"}, {"name": "דניאל"}]}
    found = resolve_employee(profile, "דן")
    assert found["found"] is True
    assert found["ambiguous"] is False


def test_an_unknown_name_is_not_ambiguous_it_is_absent():
    """Two different questions: "which one" versus "who is that".

    Kept apart because they are asked differently, and because reporting an
    unknown name as ambiguous would offer the manager a choice between no
    options at all.
    """
    found = resolve_employee(PROFILE, "אבישי")
    assert found["found"] is False
    assert found["ambiguous"] is False
    assert found["matches"] == []


# -- the write path: ambiguity is a gate -----------------------------------

def test_an_ambiguous_employee_withdraws_the_operations():
    """Two Daniels, one request, and nothing queued behind the question.

    The model is *scripted to be confident* here — it returns an operation
    and claims no ambiguity. Code catches it anyway, which is the point: this
    is the same enforcement `needs_reason` gets, not a prompt instruction.
    """
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_ASSIGN, "employee": "דניאל",
                     "shift": MORNING, "date": "2026-08-20",
                     "reason": "פנוי"}],
        agent_reason="הכי פנוי",
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "תשבץ את דניאל", stated_reason="כיסוי",
    )
    assert proposal["needs_input"] is True
    assert proposal["operations"] == []


def test_the_question_names_both_candidates_when_the_model_asked_nothing():
    """A held proposal with nothing said reads as a request being ignored."""
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_ASSIGN, "employee": "דניאל",
                     "shift": MORNING, "date": "2026-08-20", "reason": "פנוי"}],
        agent_reason="נימוק", reply="",
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "תשבץ את דניאל", stated_reason="כיסוי",
    )
    assert DANIEL_C in proposal["reply"]
    assert DANIEL_L in proposal["reply"]


def test_an_employee_the_roster_does_not_carry_withdraws_the_operations():
    """The invented-person case. A name nobody has is never a target."""
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_ASSIGN, "employee": "אבישי",
                     "shift": MORNING, "date": "2026-08-20", "reason": "פנוי"}],
        agent_reason="נימוק",
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "תשבץ את אבישי", stated_reason="כיסוי",
    )
    assert proposal["needs_input"] is True
    assert proposal["operations"] == []


def test_the_other_half_of_a_swap_is_checked_too():
    """A swap touches two people, so it can be ambiguous on either side."""
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_SWAP, "employee": MOSHE,
                     "shift": MORNING, "date": "2026-08-20",
                     "with_employee": "דניאל", "with_shift": MORNING,
                     "with_date": "2026-08-21", "reason": "החלפה"}],
        agent_reason="נימוק",
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "תחליף בין משה לדניאל", stated_reason="בקשה",
    )
    assert proposal["needs_input"] is True
    assert proposal["operations"] == []


def test_a_clear_request_still_goes_through_untouched():
    """The regression this whole change must not cause.

    An unambiguous name, a real slot, a stated reason — nothing about asking
    when unsure may make the ordinary path ask.
    """
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_ASSIGN, "employee": MOSHE,
                     "shift": MORNING, "date": "2026-08-21",
                     "reason": "משה ב-12 שעות, הכי פחות בצוות"}],
        agent_reason="משה הכי פנוי ומוסמך לבוקר",
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "תשבץ את משה לבוקר ב-21.8", stated_reason="כיסוי",
    )
    assert proposal["needs_input"] is False
    assert proposal["needs_reason"] is False
    assert len(proposal["operations"]) == 1


def test_the_model_may_ask_on_its_own_and_nothing_is_queued():
    """A missing shift is the model's call — code cannot see that one.

    Which of three shifts "תשבץ את משה" means is not something the roster can
    answer, so this gate is the prompt's. What code guarantees is the part
    that matters: `needs_input` empties the proposal whoever raised it.
    """
    llm = _ScriptedLlm([_change(
        needs_input=True, reply="לאיזו משמרת לשבץ את משה — בוקר או צהריים?",
        operations=[{"action": OP_ASSIGN, "employee": MOSHE,
                     "shift": MORNING, "date": "2026-08-20", "reason": "פנוי"}],
        agent_reason="נימוק",
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "תשבץ את משה", stated_reason="כיסוי",
    )
    assert proposal["needs_input"] is True
    assert proposal["operations"] == []
    assert "משמרת" in proposal["reply"]


def test_profile_operations_are_withheld_by_ambiguity_too():
    """A roster edit aimed at an unresolvable person is the same failure."""
    llm = _ScriptedLlm([_change(
        needs_input=True, reply="לאיזה דניאל?",
        profile_operations=[{
            "action": "update_employee", "target": DANIEL_C,
            "item": {"name": DANIEL_C, "role": "אחראי משמרת",
                     "eligible_shifts": [], "start_time": "", "end_time": "",
                     "headcount": 1, "is_on_call": False},
        }],
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "תעדכן את דניאל לאחראי משמרת",
    )
    assert proposal["needs_input"] is True
    assert proposal["profile_operations"] == []


def test_only_one_question_is_asked_at_a_time():
    """Target first, reason after. Two questions at once get neither answered.

    A manager asked "which דניאל, and also why?" has been handed a form. The
    reason is worth collecting only once there is a settled person to record
    it against.
    """
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_REMOVE, "employee": "דניאל",
                     "shift": MORNING, "date": "2026-08-20", "reason": ""}],
        needs_reason=True, reply="",
    )])
    proposal = ChangeAgent(llm).propose(PROFILE, SCHEDULE, "תוריד את דניאל")
    assert proposal["needs_input"] is True
    assert proposal["needs_reason"] is False


# -- resuming: the answer continues the request ----------------------------

def test_the_clarification_reaches_the_model_with_the_original_request():
    """The manager answers "ערב"; the model is asked about both halves.

    This is what makes the interaction worth having. Sending only "ערב" would
    make the agent re-derive an intent from one word, which is how a
    clarification turns into a new, emptier question.
    """
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_ASSIGN, "employee": MOSHE,
                     "shift": EVENING, "date": "2026-08-20", "reason": "פנוי"}],
        agent_reason="נימוק",
    )])
    ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "צהריים",
        stated_reason="כיסוי", pending_request="תשבץ את משה",
    )
    sent = llm.calls[0]["user"]
    assert "תשבץ את משה" in sent
    assert "צהריים" in sent


def test_the_model_is_told_what_it_already_asked():
    """The loop guard. A model that cannot see it asked, asks again."""
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_ASSIGN, "employee": MOSHE,
                     "shift": EVENING, "date": "2026-08-20", "reason": "פנוי"}],
        agent_reason="נימוק",
    )])
    ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "צהריים",
        stated_reason="כיסוי", pending_request="תשבץ את משה",
    )
    sent = llm.calls[0]["user"]
    assert "asked_last_turn" in sent
    assert "answer_to_that" in sent


def test_a_resolved_request_carries_nothing_pending_back():
    """An answered question cannot be reopened by a stale echo.

    The client sends back whatever `pending_request` it was given, so a
    finished proposal must clear it — otherwise the next unrelated sentence
    would be merged into a request that was already carried out.
    """
    llm = _ScriptedLlm([_change(
        operations=[{"action": OP_ASSIGN, "employee": MOSHE,
                     "shift": EVENING, "date": "2026-08-20", "reason": "פנוי"}],
        agent_reason="נימוק",
    )])
    proposal = ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "צהריים",
        stated_reason="כיסוי", pending_request="תשבץ את משה",
    )
    assert proposal["needs_input"] is False
    assert proposal["pending_request"] == ""


def test_an_open_question_carries_the_request_it_is_waiting_on():
    llm = _ScriptedLlm([_change(
        needs_input=True, reply="לאיזו משמרת?",
    )])
    proposal = ChangeAgent(llm).propose(PROFILE, SCHEDULE, "תשבץ את משה")
    assert proposal["pending_request"] == "תשבץ את משה"


def test_an_answer_that_restates_the_request_is_not_doubled():
    """A manager who retypes the whole sentence is not punished for it.

    The merge appends the answer to the held request, which for a manager who
    repeated themselves would read "תשבץ את משה (תשבץ את משה למשמרת צהריים)".
    Asserted on `request` specifically, since `answer_to_that` carries their
    words verbatim by design.
    """
    llm = _ScriptedLlm([_change(agent_reason="נימוק")])
    ChangeAgent(llm).propose(
        PROFILE, SCHEDULE, "תשבץ את משה למשמרת צהריים",
        pending_request="תשבץ את משה",
    )
    sent = json.loads(llm.calls[0]["user"])
    assert sent["request"] == "תשבץ את משה למשמרת צהריים"
