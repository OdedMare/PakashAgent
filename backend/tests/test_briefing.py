"""The agent speaking first, against a fake model.

What is pinned here is not the model's judgment — it is the line the feature
rests on: a briefing **observes and never acts**. The interesting assertions
are all about what the agent is not allowed to do, plus the two normalizations
that are decided in code rather than trusted to the prompt (`quiet`, and an
unknown trigger).
"""

import json

import pytest

from app.bl.briefing import (
    BriefingAgent,
    TRIGGER_OPENED,
    TRIGGER_PERIODIC,
    TRIGGER_PUBLISHING,
)
from app.common.errors import AgentError

MORNING = "בוקר"
EVENING = "צהריים"

PROFILE = {
    "workplace": {"name": "מוקד"},
    "employees": [{"name": "דנה"}, {"name": "יוסי"}],
    "shifts": [{
        "name": MORNING, "start_time": "07:00", "end_time": "15:00",
        "days": [], "is_on_call": False, "hour_weight": 1.0,
    }],
    "rules": [],
}

SCHEDULE = {
    "id": "sched-1",
    "status": "draft",
    "starts_on": "2026-08-17",
    "ends_on": "2026-08-23",
    "slots": [
        {"shift_name": MORNING, "slot_date": "2026-08-17", "headcount": 1},
        {"shift_name": MORNING, "slot_date": "2026-08-18", "headcount": 1},
    ],
    "assignments": [
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-17"},
    ],
    "closures": [{
        "date": "2026-08-20",
        "groups": [
            {"pattern": "round", "group": "א", "label": "סבב א"},
            {"pattern": "triplet", "group": "ג", "label": "תלתון ג"},
        ],
        "label": "סבב א ותלתון ג",
        "employees": ["דנה", "יוסי"],
        "shifts": [],
        "until_handover": False,
    }],
}


class _ScriptedLlm:
    def __init__(self, answers):
        self._answers = list(answers)
        self.calls = []

    def complete_json(self, system, user, schema=None, flow=""):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if not self._answers:
            raise AssertionError("model called more times than scripted")
        return self._answers.pop(0)


def _answer(**overrides):
    answer = {"headline": "השבוע נראה סביר", "items": [], "quiet": True}
    answer.update(overrides)
    return answer


def _item(**overrides):
    item = {
        "text": "משמרת בוקר של שלישי ריקה",
        "kind": "gap",
        "suggestion": "מי יכול לכסות את בוקר שלישי?",
    }
    item.update(overrides)
    return item


# -- the shape that comes back ---------------------------------------------

def test_a_briefing_with_items_is_not_quiet():
    """`quiet` is decided from the items, not from what the model claimed.

    A model labelling itself quiet while listing three problems would render
    an all-clear banner above a list of them.
    """
    agent = BriefingAgent(_ScriptedLlm([
        _answer(items=[_item()], quiet=True)
    ]))

    result = agent.brief(TRIGGER_OPENED, PROFILE, schedule=SCHEDULE)

    assert result["quiet"] is False
    assert len(result["items"]) == 1


def test_a_briefing_with_no_items_is_quiet():
    """And the reverse: claiming urgency while listing nothing."""
    agent = BriefingAgent(_ScriptedLlm([_answer(items=[], quiet=False)]))

    result = agent.brief(TRIGGER_OPENED, PROFILE, schedule=SCHEDULE)

    assert result["quiet"] is True
    assert result["items"] == []


def test_items_are_bounded_and_empty_text_is_dropped():
    """An item with no text is a row the manager can neither read nor act on."""
    agent = BriefingAgent(_ScriptedLlm([
        _answer(items=[
            _item(text="ראשון"), _item(text=""), _item(text="שני"),
            _item(text="שלישי"), _item(text="רביעי"), _item(text="חמישי"),
        ])
    ]))

    result = agent.brief(TRIGGER_OPENED, PROFILE, schedule=SCHEDULE)

    assert [item["text"] for item in result["items"]] == [
        "ראשון", "שני", "שלישי",
    ]


def test_an_unknown_kind_becomes_a_risk():
    agent = BriefingAgent(_ScriptedLlm([
        _answer(items=[_item(kind="שמח")])
    ]))

    result = agent.brief(TRIGGER_OPENED, PROFILE, schedule=SCHEDULE)

    assert result["items"][0]["kind"] == "risk"


def test_a_suggestion_may_be_empty():
    """An observation is allowed to just be an observation."""
    agent = BriefingAgent(_ScriptedLlm([
        _answer(items=[_item(suggestion="")])
    ]))

    result = agent.brief(TRIGGER_OPENED, PROFILE, schedule=SCHEDULE)

    assert result["items"][0]["suggestion"] == ""


# -- what a briefing may never do ------------------------------------------

def test_a_briefing_carries_no_operations():
    """The line the whole feature rests on (D15).

    Even when the model returns operation-shaped fields, nothing survives
    into the result: there is no key here that `apply` could ever read, which
    is what keeps "the agent speaks first" from becoming "the agent acts".
    """
    agent = BriefingAgent(_ScriptedLlm([{
        "headline": "העברתי את דנה",
        "items": [_item()],
        "quiet": False,
        "operations": [
            {"action": "assign", "employee": "יוסי", "shift": MORNING,
             "date": "2026-08-18", "reason": "כיסוי"},
        ],
        "constraints": [{"employee": "דנה", "date": "2026-08-18"}],
    }]))

    result = agent.brief(TRIGGER_OPENED, PROFILE, schedule=SCHEDULE)

    assert set(result) == {"headline", "items", "quiet"}
    assert "operations" not in result
    assert "constraints" not in result


def test_the_model_is_never_asked_to_count():
    """Warnings and fairness go *to* the model as computed facts.

    `audit.py` owns the arithmetic (D3) and speaking first does not move that
    line. The payload must carry the numbers rather than the raw material for
    the model to total up itself.
    """
    llm = _ScriptedLlm([_answer()])
    agent = BriefingAgent(llm)

    agent.brief(
        TRIGGER_OPENED, PROFILE, schedule=SCHEDULE,
        warnings=[{"code": "unfilled", "message": "משמרת ריקה"}],
        fairness={"average_hours": 24.0, "people": [
            {"employee": "דנה", "hours": 32.0, "delta": 8.0},
        ]},
    )

    payload = json.loads(llm.calls[0]["user"])
    assert payload["warnings"][0]["code"] == "unfilled"
    assert payload["fairness"]["average_hours"] == 24.0


def test_computed_closures_reach_clickable_improvement_suggestions():
    """The briefing reads who closes; it never tries to derive the cycle."""
    llm = _ScriptedLlm([_answer(items=[_item(
        kind="rotation",
        suggestion="הצע כיסוי מתוך סבב א ותלתון ג שסוגרים בסופ״ש.",
    )])])
    result = BriefingAgent(llm).brief(
        TRIGGER_OPENED, PROFILE, schedule=SCHEDULE,
    )

    payload = json.loads(llm.calls[0]["user"])
    assert payload["schedule"]["closures"][0]["label"] == "סבב א ותלתון ג"
    assert result["items"][0]["kind"] == "rotation"
    assert result["items"][0]["suggestion"].startswith("הצע כיסוי")


# -- the trigger -----------------------------------------------------------

@pytest.mark.parametrize("trigger", [
    TRIGGER_OPENED, TRIGGER_PUBLISHING, TRIGGER_PERIODIC,
])
def test_a_named_trigger_reaches_the_model(trigger):
    """The prompt branches on the trigger by name, so it must arrive intact."""
    llm = _ScriptedLlm([_answer()])

    BriefingAgent(llm).brief(trigger, PROFILE, schedule=SCHEDULE)

    assert json.loads(llm.calls[0]["user"])["trigger"] == trigger


def test_an_unknown_trigger_falls_back_rather_than_raising():
    """This is decoration on a screen that must render regardless."""
    llm = _ScriptedLlm([_answer()])

    BriefingAgent(llm).brief("whatever", PROFILE)

    assert json.loads(llm.calls[0]["user"])["trigger"] == TRIGGER_OPENED


def test_no_schedule_is_passed_as_null():
    """"Nothing has been built yet" is the most useful thing to say to a
    manager opening an empty control room — and an empty slot list would
    instead read as a built period with nobody on it."""
    llm = _ScriptedLlm([_answer()])

    BriefingAgent(llm).brief(TRIGGER_OPENED, PROFILE, schedule=None)

    assert json.loads(llm.calls[0]["user"])["schedule"] is None


def test_last_said_is_forwarded_so_the_agent_does_not_repeat_itself():
    llm = _ScriptedLlm([_answer()])

    BriefingAgent(llm).brief(
        TRIGGER_OPENED, PROFILE, last_said=["דנה ב-32 שעות"],
    )

    assert json.loads(llm.calls[0]["user"])["last_said"] == ["דנה ב-32 שעות"]


def test_a_malformed_model_answer_raises():
    """The service catches this and returns quiet; the agent itself is honest
    about having failed rather than inventing an all-clear."""
    agent = BriefingAgent(_ScriptedLlm([["not", "a", "dict"]]))

    with pytest.raises(AgentError):
        agent.brief(TRIGGER_OPENED, PROFILE)


def test_the_agents_build_alerts_reach_the_conversation():
    """What the agent decided while building is what it opens with.

    The alert is raised inside a build the manager was not watching, so the
    briefing is where it reaches them in words — beside, and distinct from,
    the audit's warnings about the same period (D25).
    """
    llm = _ScriptedLlm([_answer(items=[_item()], quiet=False)])

    BriefingAgent(llm).brief(
        TRIGGER_OPENED, PROFILE, schedule=SCHEDULE,
        warnings=[{
            "code": "unfilled", "severity": "warning",
            "message": "בוקר שלישי ריק", "date": "2026-08-18",
        }],
        alerts=[{
            "code": "rule_traded", "severity": "warning",
            "message": "שיבצתי את דנה יום שישי ברציפות כי לא נשאר אף אחד",
            "employee": "דנה", "date": "2026-08-17", "shift": MORNING,
            "source": "agent",
        }],
    )

    payload = json.loads(llm.calls[0]["user"])
    assert payload["alerts"][0]["code"] == "rule_traded"
    # Not folded into the warnings: they answer different questions.
    assert [row["code"] for row in payload["warnings"]] == ["unfilled"]
