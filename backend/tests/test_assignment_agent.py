"""The agent assigns; the tools count; the engine is the floor.

Three claims are the feature and each is asserted directly here:

- **The agent's choice is what gets stored**, including when it is not the
  one the ranking would have made. That is the whole difference from
  `deterministic_scheduler.py`, which cannot read a rule written in Hebrew.
- **An unusable row is refused and handed back**, not dropped. The agent
  gets one corrected turn, and what it corrects is what lands.
- **A rule traded away is loud.** Every cost the agent accepts and every
  slot it leaves short comes back as an alert, whether or not the agent
  mentioned it — the loud warning D1/D3 promise instead of a gate.
"""

import json

import pytest

from app.bl.assignment_agent import (
    ALERT_COST,
    ALERT_REJECTED,
    ALERT_UNFILLED,
    AssignmentAgent,
)
from app.bl.assignment_tools import DayDraft
from app.bl.scheduler import build_slots
from app.common.errors import AgentError

MORNING = "בוקר"
EVENING = "ערב"
DAY = "2026-08-17"


def _profile(headcount=1, employees=None):
    return {
        "workplace": {"name": "מוקד", "mission": "מענה"},
        "employees": employees or [
            {"name": "דנה", "eligible_shifts": [MORNING]},
            {"name": "יוסי", "eligible_shifts": [MORNING]},
            {"name": "רון", "eligible_shifts": [MORNING]},
        ],
        "shifts": [{
            "name": MORNING, "start_time": "07:00", "end_time": "15:00",
            "days": [], "is_on_call": False, "hour_weight": 1.0,
            "staffing": [{
                "days": [], "headcount": headcount, "required_roles": [],
            }],
        }],
        "rules": [
            {"text": "רון לא נכנס לבוקר אחרי לילה", "severity": "soft"},
        ],
    }


class _ScriptedLlm:
    """Answers in order. Records what it was asked, so payloads are testable."""

    def __init__(self, answers=None):
        self._answers = list(answers or [])
        self.calls = []

    def complete_json(self, system, user, schema=None, flow=""):
        self.calls.append({
            "system": system, "payload": json.loads(user), "flow": flow,
        })
        if not self._answers:
            raise AssertionError("model called more times than scripted")
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _answer(assignments=None, alerts=None, tool_calls=None, done=True):
    return {
        "done": done,
        "tool_calls": tool_calls or [],
        "assignments": assignments or [],
        "alerts": alerts or [],
        "notes": [],
        "summary": "שובץ",
    }


def _row(employee, reason="הכי פחות שעות השבוע", shift=MORNING):
    return {"employee": employee, "shift": shift, "reason": reason}


# -- the agent decides -----------------------------------------------------

def test_the_agent_picks_who_works_and_its_choice_is_stored():
    """Not the ranking's first name — the agent's.

    `רון` is last in a tie the code breaks alphabetically, so a schedule
    that lands on him can only have come from the agent choosing. That is
    the point of the whole module: the manager's rules are Hebrew sentences
    and no ranking function can read one.
    """
    llm = _ScriptedLlm([_answer([_row("רון", "רון ותיק והערב עמוס")])])

    result = AssignmentAgent(llm).generate_day(_profile(), DAY)

    assert [row["employee"] for row in result["assignments"]] == ["רון"]
    assert result["assignments"][0]["reason"] == "רון ותיק והערב עמוס"
    assert result["metrics"]["engine"] == "agent"


def test_the_agent_reads_the_rules_and_the_manager_instruction():
    """Both travel verbatim: they are the half no tool can answer (D2)."""
    llm = _ScriptedLlm([_answer([_row("דנה")])])

    AssignmentAgent(llm).generate_day(
        _profile(), DAY,
        instructions="דנה חוזרת ממילואים, אל תעמיסו עליה",
        preferences=[{
            "kind": "employee", "subject": "יוסי", "text": "יוסי מעדיף בוקר",
        }],
    )

    payload = llm.calls[0]["payload"]
    assert payload["instructions"] == "דנה חוזרת ממילואים, אל תעמיסו עליה"
    assert payload["preferences"][0]["text"] == "יוסי מעדיף בוקר"
    assert payload["profile"]["rules"][0]["text"] == (
        "רון לא נכנס לבוקר אחרי לילה"
    )


def test_the_candidates_arrive_counted_so_the_agent_never_counts():
    """Everything countable is answered before the first turn (D3)."""
    llm = _ScriptedLlm([_answer([_row("דנה")])])

    AssignmentAgent(llm).generate_day(
        _profile(), DAY,
        history=[
            {"employee": "דנה", "shift": MORNING, "date": "2026-08-10"},
        ],
    )

    payload = llm.calls[0]["payload"]
    assert payload["open_slots"][0]["missing"] == 1
    names = [
        item["employee"] for item in payload["candidates"][0]["candidates"]
    ]
    assert names == ["יוסי", "רון", "דנה"]  # ranked by load, דנה carries 8h
    assert {
        row["employee"]: row["hours"] for row in payload["workload"]
    }["דנה"] == 8.0


def test_the_agent_can_ask_a_tool_before_it_answers():
    """Ask, get arithmetic back, then decide — the `planner.py` shape."""
    llm = _ScriptedLlm([
        _answer(tool_calls=[{
            "tool": "check_placement",
            "arguments": {"employee": "רון", "shift": MORNING},
        }], done=False),
        _answer([_row("רון")]),
    ])

    result = AssignmentAgent(llm).generate_day(_profile(), DAY)

    assert result["steps"][0]["tool"] == "check_placement"
    assert llm.calls[1]["payload"]["results"][0]["ok"] is True
    assert [row["employee"] for row in result["assignments"]] == ["רון"]


# -- code refuses what cannot stand ----------------------------------------

def test_a_row_against_a_hard_constraint_is_refused_and_handed_back():
    """The refusal is a sentence the next turn can act on, not a silent drop."""
    llm = _ScriptedLlm([
        _answer([_row("דנה", "דנה מוסמכת")]),
        _answer([_row("יוסי", "יוסי פנוי במקומה")]),
    ])

    result = AssignmentAgent(llm).generate_day(
        _profile(), DAY,
        availability=[{
            "employee": "דנה", "date": DAY, "available": False,
            "is_hard": True, "reason": "מחלה",
        }],
    )

    assert [row["employee"] for row in result["assignments"]] == ["יוסי"]
    repair = llm.calls[1]["payload"]["repair"]
    assert repair["rejected_rows"][0]["row"]["employee"] == "דנה"
    assert "אילוץ קשיח" in repair["rejected_rows"][0]["reason"]
    # Nothing is left over: the corrected answer is the one that stands, so
    # a refusal the agent went on to fix is not a thing to alert about.
    assert not [
        alert for alert in result["alerts"] if alert["code"] == ALERT_REJECTED
    ]


def test_a_refusal_the_agent_never_fixed_is_told_to_the_manager():
    """The last answer is the one that counts — including what it got wrong."""
    llm = _ScriptedLlm([
        _answer([_row("דנה"), _row("מישהו")]),
        _answer([_row("דנה"), _row("מישהו")]),
    ])

    result = AssignmentAgent(llm).generate_day(_profile(headcount=2), DAY)

    rejected = [
        alert for alert in result["alerts"] if alert["code"] == ALERT_REJECTED
    ]
    assert rejected and rejected[0]["employee"] == "מישהו"
    assert rejected[0]["severity"] == "info"


def test_a_row_with_no_reason_is_not_stored():
    """D8 in code, not in the prompt."""
    llm = _ScriptedLlm([
        _answer([{"employee": "דנה", "shift": MORNING, "reason": ""}]),
        _answer([_row("דנה", "דנה מוסמכת לבוקר")]),
    ])

    result = AssignmentAgent(llm).generate_day(_profile(), DAY)

    assert result["assignments"][0]["reason"] == "דנה מוסמכת לבוקר"
    assert "נימוק" in llm.calls[1]["payload"]["repair"]["rejected_rows"][0][
        "reason"
    ]


def test_a_person_nobody_declared_is_refused():
    llm = _ScriptedLlm([
        _answer([_row("מישהו")]),
        _answer([_row("דנה")]),
    ])

    result = AssignmentAgent(llm).generate_day(_profile(), DAY)

    assert [row["employee"] for row in result["assignments"]] == ["דנה"]


def test_the_managers_pin_survives_a_repair_turn():
    """A re-answer is the agent's to redo; the pin was never the agent's."""
    llm = _ScriptedLlm([
        _answer([_row("מישהו")]),
        _answer([_row("יוסי")]),
    ])

    result = AssignmentAgent(llm).generate_day(
        _profile(headcount=2), DAY,
        required_assignments=[{
            "employee": "דנה", "shift": MORNING, "date": DAY,
        }],
    )

    placed = {row["employee"] for row in result["assignments"]}
    assert placed == {"דנה", "יוסי"}
    assert "שיבוץ חובה" in next(
        row["reason"] for row in result["assignments"]
        if row["employee"] == "דנה"
    )


# -- an expensive choice is allowed, and loud ------------------------------

def test_a_cost_the_agent_accepts_becomes_an_alert_with_its_reason():
    """The audit still does not block — it speaks up (D1/D3)."""
    llm = _ScriptedLlm([
        _answer(
            [_row("דנה", "אין אף אחד אחר שמוסמך לבוקר")],
            alerts=[{
                "severity": "warning",
                "message": "דנה עוברת את תקרת השעות שלה השבוע",
                "employee": "דנה",
            }],
        ),
    ])

    result = AssignmentAgent(llm).generate_day(
        _profile(), DAY,
        availability=[{
            "employee": "דנה", "date": DAY, "available": False,
            "is_hard": False, "reason": "מעדיפה לא",
        }],
    )

    assert [row["employee"] for row in result["assignments"]] == ["דנה"]
    traded = [
        alert for alert in result["alerts"] if alert["code"] == ALERT_COST
    ]
    assert traded and "העדפה" in traded[0]["message"]
    # The agent's own reason travels with the alert: "why did it do that" is
    # the manager's first question and the answer was already written.
    assert "אין אף אחד אחר" in traded[0]["message"]
    assert any(alert["source"] == "agent" for alert in result["alerts"])


def test_a_slot_left_short_is_alerted_with_who_was_free():
    llm = _ScriptedLlm([
        _answer([_row("דנה")]),
        _answer([_row("דנה")]),
    ])

    result = AssignmentAgent(llm).generate_day(_profile(headcount=3), DAY)

    short = [
        alert for alert in result["alerts"] if alert["code"] == ALERT_UNFILLED
    ]
    assert short and "יוסי" in short[0]["message"]
    assert short[0]["severity"] == "warning"


def test_a_short_slot_with_nobody_legal_says_so():
    llm = _ScriptedLlm([_answer([_row("דנה")]), _answer([_row("דנה")])])

    result = AssignmentAgent(llm).generate_day(
        _profile(headcount=2), DAY,
        availability=[
            {"employee": name, "date": DAY, "available": False,
             "is_hard": True, "reason": "לא זמין"}
            for name in ("יוסי", "רון")
        ],
    )

    short = [
        alert for alert in result["alerts"] if alert["code"] == ALERT_UNFILLED
    ]
    assert short and "אין אף אחד" in short[0]["message"]


def test_one_repair_and_no_more():
    """A second short answer is a decision, not an invitation to loop."""
    llm = _ScriptedLlm([
        _answer([_row("דנה")]),
        _answer([_row("דנה")]),
    ])

    AssignmentAgent(llm).generate_day(_profile(headcount=2), DAY)

    assert len(llm.calls) == 2


# -- when the agent cannot answer ------------------------------------------

def test_an_unreachable_model_raises_so_the_engine_can_take_over():
    llm = _ScriptedLlm([AgentError("לא הוגדר חיבור למודל")])

    with pytest.raises(AgentError):
        AssignmentAgent(llm).generate_day(_profile(), DAY)


def test_an_empty_answer_on_a_fillable_day_is_a_failure_not_a_decision():
    llm = _ScriptedLlm([_answer([]), _answer([])])

    with pytest.raises(AgentError):
        AssignmentAgent(llm).generate_day(_profile(), DAY)


def test_a_day_nobody_could_work_comes_back_empty_rather_than_failing():
    llm = _ScriptedLlm([_answer([])])

    result = AssignmentAgent(llm).generate_day(
        _profile(), DAY,
        availability=[
            {"employee": name, "date": DAY, "available": False,
             "is_hard": True, "reason": "לא זמין"}
            for name in ("דנה", "יוסי", "רון")
        ],
    )

    assert result["assignments"] == []
    assert any(
        alert["code"] == ALERT_UNFILLED for alert in result["alerts"]
    )


# -- the tools themselves --------------------------------------------------

def test_the_tool_dispatch_offers_reads_and_nothing_else():
    """`apply` is the loop's, not the model's: `run` cannot name it."""
    profile = _profile()
    draft = DayDraft(profile, DAY, build_slots(profile, DAY, DAY))

    assert draft.run("apply", {})["ok"] is False
    assert draft.run("open_slots")["ok"] is True
    assert draft.run("candidates", {})["ok"] is False


def test_a_blocked_candidate_comes_back_named_with_the_reason():
    """"Nobody legal is left" is a sentence only a blocked list can produce."""
    profile = _profile()
    draft = DayDraft(
        profile, DAY, build_slots(profile, DAY, DAY),
        availability=[{
            "employee": "דנה", "date": DAY, "available": False,
            "is_hard": True, "reason": "מחלה",
        }],
    )

    answer = draft.candidates(MORNING)

    assert [item["employee"] for item in answer["blocked"]] == ["דנה"]
    assert "אילוץ קשיח" in answer["blocked"][0]["reasons"][0]["message"]
    assert [item["employee"] for item in answer["candidates"]] == [
        "יוסי", "רון",
    ]


def test_a_cost_is_reported_without_blocking_the_candidate():
    profile = _profile()
    draft = DayDraft(
        profile, DAY, build_slots(profile, DAY, DAY),
        availability=[{
            "employee": "דנה", "date": DAY, "available": False,
            "is_hard": False, "reason": "מעדיפה לא",
        }],
    )

    verdict = draft.check_placement("דנה", MORNING)

    assert verdict["ok"] is True
    assert verdict["blocking"] is False
    assert "מעדיפה לא" in verdict["costs"][0]["message"]
