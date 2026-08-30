"""The planning loop, with a fake model and with none at all.

Two halves, and the second is the one that matters most:

- **With a model**, the loop runs tools the model names, feeds the results
  back, and stops. What is asserted is that the *tools* produce the facts —
  the model is never the source of a number, a name or a verdict.
- **Without a model**, the same tools run, chosen by `bl/intent.py`. This is
  the path a deployment with nothing configured takes, and `README.md`
  promises it works. Every question shape the fallback claims to answer is
  tested against real tool output rather than a stub.

Neither half can write. The repository fake counts mutations and the count
stays zero throughout, which is the property that makes it safe for the
answering path to exist at all.
"""

import datetime

import pytest

from app.bl.planner import PlanningAgent
from app.bl.tools import (
    TOOL_EMPLOYEE_STATE,
    TOOL_FIND_REPLACEMENTS,
    ScheduleTools,
)
from app.common.errors import AgentError, NotFoundError

TEAM = "team-a"

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

# A Sunday-to-Saturday week. The 22nd is its Saturday.
DATES = ["2026-08-%02d" % day for day in range(16, 23)]


class _Repo:
    def __init__(self):
        self.writes = 0
        self.schedules = {}
        self.availability_rows = []

    def team_profile(self, team_id):
        return PROFILE if team_id == TEAM else None

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
            if row["team_id"] == team_id:
                return row
        return None

    def availability(self, team_id, starts_on=None, ends_on=None, employee=None):
        return [
            row for row in self.availability_rows if row["team_id"] == TEAM
        ]

    # Writes, which nothing on the answering path may reach.
    def add_assignment(self, *a, **k):
        self.writes += 1

    def remove_assignment(self, *a, **k):
        self.writes += 1

    def move_assignment(self, *a, **k):
        self.writes += 1

    def append_change(self, *a, **k):
        self.writes += 1

    def set_availability(self, *a, **k):
        self.writes += 1


class _NoModel:
    """A model that is not configured — what an empty deployment has.

    Raises exactly what `dal/llm` raises when there is no key and no base
    URL, so the fallback is exercised through the real failure rather than a
    convenient one.
    """

    def complete_json(self, *args, **kwargs):
        raise AgentError("לא הוגדר מפתח API או שרת תואם OpenAI")


class _BrokenAdapter:
    """A compatible provider that fails before it can shape its error."""

    def complete_json(self, *args, **kwargs):
        raise RuntimeError("adapter setup failed")


class _ScriptedModel:
    """Replays prepared turns, recording what it was asked."""

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []

    def complete_json(self, prompt, payload, schema=None, flow=None):
        self.calls.append(payload)
        if not self._turns:
            return {"done": True, "answer": "סיימתי.", "tool_calls": [],
                    "needs_confirmation": False}
        return self._turns.pop(0)


@pytest.fixture
def repo():
    repo = _Repo()
    slots = []
    for date in DATES:
        for shift in (MORNING, EVENING):
            slots.append({
                "id": "slot-%s-%s" % (shift, date),
                "shift_name": shift, "slot_date": date,
                "start_time": "07:00" if shift == MORNING else "15:00",
                "end_time": "15:00" if shift == MORNING else "23:00",
                "headcount": 1, "is_on_call": False,
            })
    repo.schedules["sched-1"] = {
        "id": "sched-1", "team_id": TEAM,
        "starts_on": DATES[0], "ends_on": DATES[-1], "status": "draft",
        "slots": slots,
        "assignments": [{
            "id": "asg-1", "slot_id": "slot-%s-%s" % (EVENING, DATES[6]),
            "employee": YOSSI, "shift": EVENING, "date": DATES[6],
            "reason": "בדיקה", "source": "agent",
        }],
    }
    return repo


@pytest.fixture
def tools(repo):
    return ScheduleTools(repo)


# -- with a model ----------------------------------------------------------


def test_the_loop_runs_the_tools_the_model_names(repo, tools):
    model = _ScriptedModel([
        {
            "done": False, "answer": "", "needs_confirmation": False,
            "tool_calls": [{
                "tool": TOOL_EMPLOYEE_STATE,
                "arguments": {"employee": YOSSI, "day": DATES[6]},
            }],
        },
        {
            "done": True, "needs_confirmation": True,
            "answer": "ליוסי יש משמרת אחת בשבת.", "tool_calls": [],
        },
    ])
    answer = PlanningAgent(model, tools).answer(
        TEAM, "מי יכול להחליף את יוסי בשבת", PROFILE,
    )
    assert answer["used_model"] is True
    assert answer["answer"] == "ליוסי יש משמרת אחת בשבת."
    assert [step["tool"] for step in answer["steps"]] == [TOOL_EMPLOYEE_STATE]
    # The tool's own output is what came back, not the model's account of it.
    assert answer["results"][0]["found"] is True
    assert answer["results"][0]["shifts"][0]["shift"] == EVENING


def test_the_loop_is_bounded_when_the_model_never_finishes(repo, tools):
    """A model that keeps asking for one more tool must still terminate."""
    forever = {
        "done": False, "answer": "עוד רגע", "needs_confirmation": False,
        "tool_calls": [{"tool": TOOL_EMPLOYEE_STATE,
                        "arguments": {"employee": YOSSI}}],
    }
    model = _ScriptedModel([forever] * 20)
    answer = PlanningAgent(model, tools).answer(TEAM, "שאלה", PROFILE)
    # Three turns, one tool each.
    assert len(answer["steps"]) <= 3


def test_a_question_carries_recommended_clickable_options(repo, tools):
    model = _ScriptedModel([{
        "done": True,
        "answer": "צריך לבחור את היום שהתכוונת אליו.",
        "question": {
            "question": "לאיזה יום התכוונת?",
            "recommendation": "התכוונתי ליום שלישי, 25.8.",
            "why": "בחירת יום אחר תשנה את המשמרת שנבדוק.",
            "options": [
                {"label": "שלישי 25.8", "answer": "התכוונתי ליום שלישי, 25.8."},
                {"label": "רביעי 26.8", "answer": "התכוונתי ליום רביעי, 26.8."},
            ],
        },
        "needs_input": True,
        "needs_confirmation": False,
        "tool_calls": [],
    }])

    answer = PlanningAgent(model, tools).answer(TEAM, "מי עובד באמצע השבוע", PROFILE)

    assert answer["needs_input"] is True
    assert answer["question"]["options"][0] == {
        "label": "שלישי 25.8",
        "answer": "התכוונתי ליום שלישי, 25.8.",
    }


def test_a_tool_the_menu_does_not_have_is_never_run(repo, tools):
    model = _ScriptedModel([
        {
            "done": False, "answer": "", "needs_confirmation": False,
            "tool_calls": [{"tool": "delete_everything", "arguments": {}}],
        },
        {"done": True, "answer": "בסדר", "tool_calls": [],
         "needs_confirmation": False},
    ])
    answer = PlanningAgent(model, tools).answer(TEAM, "שאלה", PROFILE)
    assert answer["steps"] == []


def test_answering_never_writes(repo, tools):
    model = _ScriptedModel([
        {
            "done": False, "answer": "", "needs_confirmation": False,
            "tool_calls": [
                {"tool": TOOL_EMPLOYEE_STATE, "arguments": {"employee": YOSSI}},
                {"tool": TOOL_FIND_REPLACEMENTS, "arguments": {
                    "employee": YOSSI, "shift_name": EVENING,
                    "slot_date": DATES[6]}},
            ],
        },
        {"done": True, "answer": "רון יכול.", "tool_calls": [],
         "needs_confirmation": True},
    ])
    PlanningAgent(model, tools).answer(TEAM, "מי יכול להחליף את יוסי", PROFILE)
    assert repo.writes == 0


def test_an_empty_request_is_refused(repo, tools):
    with pytest.raises(AgentError):
        PlanningAgent(_ScriptedModel([]), tools).answer(TEAM, "   ", PROFILE)


def test_an_unexpected_adapter_failure_uses_the_no_model_fallback(repo, tools):
    answer = PlanningAgent(_BrokenAdapter(), tools).answer(
        TEAM, "מי בצוות", PROFILE,
    )

    assert answer["used_model"] is False
    assert answer["understood"] is True
    assert "3" in answer["answer"]


def test_only_active_preferences_reach_the_model(repo, tools):
    """A suggested preference is inert until approved — including here."""
    model = _ScriptedModel([
        {"done": True, "answer": "בסדר", "tool_calls": [],
         "needs_confirmation": False},
    ])
    PlanningAgent(model, tools).answer(
        TEAM, "שאלה", PROFILE,
        preferences=[{"kind": "staffing", "subject": "", "text": "יוסי לפני רון"}],
    )
    assert "יוסי לפני רון" in model.calls[0]


# -- without a model -------------------------------------------------------


def test_replacements_are_found_with_no_model_configured(repo, tools):
    """The headline promise: this works with nothing configured."""
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(
        TEAM, "מי יכול להחליף את יוסי בשבת", PROFILE,
        period=repo.schedules["sched-1"],
    )
    assert answer["used_model"] is False
    assert answer["understood"] is True
    # רון is the qualified free colleague; the answer names him.
    assert RON in answer["answer"]
    assert [step["tool"] for step in answer["steps"]][0] == TOOL_EMPLOYEE_STATE
    assert TOOL_FIND_REPLACEMENTS in [step["tool"] for step in answer["steps"]]


def test_fallback_resolves_tomorrow_before_calling_a_tool(
    repo, tools, monkeypatch,
):
    monkeypatch.setattr(
        "app.bl.planner.israel_today", lambda: datetime.date(2026, 8, 20)
    )

    answer = PlanningAgent(_NoModel(), tools).answer(
        TEAM, "יוסי לא מגיע מחר", PROFILE, period=repo.schedules["sched-1"],
    )

    assert answer["steps"][0]["arguments"]["day"] == "2026-08-21"


def test_the_fallback_answer_rests_on_real_tool_output(repo, tools):
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(
        TEAM, "מי יכול להחליף את יוסי בשבת", PROFILE,
        period=repo.schedules["sched-1"],
    )
    replacements = [
        row for row in answer["results"]
        if row.get("tool") == TOOL_FIND_REPLACEMENTS
    ]
    assert replacements
    assert RON in [row["employee"] for row in replacements[0]["candidates"]]


def test_gaps_are_answered_with_no_model(repo, tools):
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(TEAM, "מה חסר בסידור", PROFILE,
                          period=repo.schedules["sched-1"])
    assert answer["understood"] is True
    # Fourteen slots, one filled.
    assert "13" in answer["answer"]


def test_one_employee_is_answered_with_no_model(repo, tools):
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(TEAM, "כמה שעות יש ליוסי", PROFILE,
                          period=repo.schedules["sched-1"])
    assert answer["understood"] is True
    assert "8" in answer["answer"]


def test_team_information_is_answered_with_no_model(repo, tools):
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(TEAM, "מי נמצא בצוות ומה התפקיד של כל אחד?", PROFILE)
    assert answer["understood"] is True
    assert DANA in answer["answer"] and "מוקדנית" in answer["answer"]
    assert answer["steps"][0]["tool"] == "team_overview"


def test_publish_readiness_is_answered_with_no_model(repo, tools):
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(TEAM, "מה חסר לפני פרסום", PROFILE,
                          period=repo.schedules["sched-1"])
    assert answer["understood"] is True
    # It says outright that these are notes rather than blocks (D3).
    assert "חסימות" in answer["answer"]


def test_the_period_is_described_with_no_model(repo, tools):
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(TEAM, "תראה לי את השבוע", PROFILE,
                          period=repo.schedules["sched-1"])
    assert answer["understood"] is True
    assert DATES[0] in answer["answer"]


def test_an_unreadable_sentence_says_so_and_lists_what_it_can_do(repo, tools):
    """It does not guess, and it does not leave the manager with nothing."""
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(TEAM, "מה שלומך", PROFILE,
                          period=repo.schedules["sched-1"])
    assert answer["understood"] is False
    assert answer["used_model"] is False
    # It asks one focused question rather than ending the conversation with a
    # capability dump or guessing what the manager meant.
    assert answer["needs_input"] is True
    assert answer["answer"].endswith("?")


def test_an_unknown_person_is_not_invented_in_the_fallback(repo, tools):
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(TEAM, "מי יכול להחליף את שרה בשבת", PROFILE,
                          period=repo.schedules["sched-1"])
    # No roster name matched, so it asks rather than picking somebody.
    assert "לא זיהיתי" in answer["answer"]


def test_somebody_with_no_shifts_has_nobody_to_replace(repo, tools):
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(TEAM, "מי יכול להחליף את דנה בשבת", PROFILE,
                          period=repo.schedules["sched-1"])
    assert "אין" in answer["answer"]


def test_the_fallback_never_writes(repo, tools):
    agent = PlanningAgent(_NoModel(), tools)
    for sentence in [
        "מי יכול להחליף את יוסי בשבת",
        "מה חסר בסידור",
        "כמה שעות יש ליוסי",
        "מה חסר לפני פרסום",
        "תראה לי את השבוע",
        "דנה חולה ביום חמישי",
    ]:
        agent.answer(TEAM, sentence, PROFILE,
                     period=repo.schedules["sched-1"])
    assert repo.writes == 0


def test_a_change_shaped_question_says_it_needs_confirmation(repo, tools):
    """Nothing has happened, and the answer says so."""
    agent = PlanningAgent(_NoModel(), tools)
    answer = agent.answer(TEAM, "מי יכול להחליף את יוסי בשבת", PROFILE,
                          period=repo.schedules["sched-1"])
    assert answer["needs_confirmation"] is True
    assert "לאשר" in answer["answer"]


def test_a_broken_model_falls_back_rather_than_failing(repo, tools):
    """A model that answers with rubbish is the same case as none at all."""

    class _Broken:
        def complete_json(self, *args, **kwargs):
            raise AgentError("המודל החזיר JSON לא תקין פעמיים")

    answer = PlanningAgent(_Broken(), tools).answer(
        TEAM, "מה חסר בסידור", PROFILE, period=repo.schedules["sched-1"],
    )
    assert answer["used_model"] is False
    assert answer["understood"] is True
