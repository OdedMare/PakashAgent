"""The translating agent: looks with tools, answers once, and code decides."""

import json

from app.bl.directive_agent import MAX_TURNS, DirectiveAgent
from app.bl.directive_agent.tools import TranslationTools
from app.bl.scheduler.scheduler import Scheduler
from app.common.errors import AgentError


MORNING, NIGHT = "בוקר", "לילה"
SUNDAY, SATURDAY = "2026-08-16", "2026-08-22"
SOURCE = [{"id": "source-1", "kind": "instructions", "context": "", "text": "..."}]


def _profile():
    return {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": "דנה"}, {"name": "דניאל"}, {"name": "יוסי"},
                      {"name": "רון", "eligible_shifts": [MORNING]}],
        "shifts": [
            {"name": MORNING, "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
            {"name": NIGHT, "start_time": "23:00", "end_time": "07:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
        ],
    }


class _ScriptedLlm:
    def __init__(self, answers):
        self.answers, self.payloads = list(answers), []

    def complete_json(self, system, user, schema=None, **kwargs):
        self.payloads.append(json.loads(user))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _turn(calls=(), directives=(), requests=(), unresolved=()):
    return {"calls": list(calls), "directives": list(directives),
            "requests": list(requests), "unresolved": list(unresolved)}


def _avoid(employee="דנה", **overrides):
    row = {"source_id": "source-1", "kind": "avoid", "employees": [employee],
           "shifts": [NIGHT], "dates": [], "weekdays": ["שני"], "count": None,
           "per": "period", "is_hard": False, "weight": 1, "reason": "עדיף בלי לילות שני"}
    row.update(overrides)
    return row


def _translate(llm, instructions="עדיף שדנה לא תעבוד בלילות שני", **kwargs):
    return DirectiveAgent(llm).translate(_profile(), SUNDAY, SATURDAY,
                                         instructions=instructions, **kwargs)


def test_the_agent_looks_with_tools_then_answers():
    llm = _ScriptedLlm([
        _turn(calls=[{"tool": "resolve_employee", "arguments": {"name": "דנה"}},
                     {"tool": "list_slots", "arguments": {"weekdays": ["שני"], "shifts": [NIGHT]}}]),
        _turn(requests=[_avoid()]),
    ])

    translated = _translate(llm)

    assert translated["requests"][0]["kind"] == "avoid"
    assert translated["model_calls"] == 2
    assert translated["steps"] == ["resolve_employee", "list_slots"]
    results = {row["tool"]: row for row in llm.payloads[1]["results"]}
    assert results["resolve_employee"]["matches"] == ["דנה"]
    assert results["list_slots"]["slots"] == [
        {"date": "2026-08-17", "weekday": "יום שני", "shift": NIGHT}]


def test_a_refused_answer_comes_back_with_the_reasons_and_can_be_fixed():
    llm = _ScriptedLlm([_turn(requests=[_avoid("נעמה")]), _turn(requests=[_avoid()])])

    translated = _translate(llm)

    assert translated is not None and translated["model_calls"] == 2
    verdict = llm.payloads[1]["results"][0]
    assert verdict["tool"] == "check" and not verdict["ok"]
    assert any("נעמה" in problem for problem in verdict["problems"])


def test_an_unresolved_source_ends_the_translation_at_once():
    llm = _ScriptedLlm([_turn(unresolved=[{"source_id": "source-1", "reason": "כללי מדי"}])])

    assert _translate(llm) is None
    assert len(llm.payloads) == 1


def test_the_loop_is_bounded_and_the_last_turn_says_so():
    looking = _turn(calls=[{"tool": "list_slots", "arguments": {}}])
    llm = _ScriptedLlm([looking] * MAX_TURNS)

    assert _translate(llm) is None
    assert len(llm.payloads) == MAX_TURNS
    assert [payload["final_turn"] for payload in llm.payloads] == [False] * (MAX_TURNS - 1) + [True]


def test_dry_runs_are_limited():
    dry = {"tool": "dry_run", "arguments": {"requests": [_avoid()]}}
    llm = _ScriptedLlm([_turn(calls=[dry, dry, dry]), _turn(requests=[_avoid()])])

    _translate(llm)

    outcomes = llm.payloads[1]["results"]
    assert [row.get("error", "") for row in outcomes][-1].startswith("dry run limit")
    assert sum(1 for row in outcomes if "assignments" in row) == 2


def test_an_unreachable_model_means_no_translation():
    assert _translate(_ScriptedLlm([AgentError("המודל לא זמין")])) is None


def test_nothing_to_translate_costs_no_call():
    llm = _ScriptedLlm([])
    assert _translate(llm, instructions="") is None
    assert llm.payloads == []


# -- the tools ---------------------------------------------------------------

def _tools(**kwargs):
    return TranslationTools(_profile(), SUNDAY, SATURDAY, SOURCE, **kwargs)


def test_resolve_employee_reports_several_matches_rather_than_choosing():
    result = _tools().run("resolve_employee", {"name": "דנ"})
    assert result["ambiguous"] and result["matches"] == ["דנה", "דניאל"]


def test_employee_state_shows_eligibility_and_hard_absence():
    tools = _tools(availability=[{"employee": "רון", "date": SUNDAY, "available": False,
                                  "is_hard": True, "reason": "חופשה"}])
    state = tools.run("employee_state", {"name": "רון"})
    assert state["eligible_shifts"] == [MORNING]
    assert state["hard_unavailable"][0]["date"] == SUNDAY


def test_check_names_each_refusal_and_the_sources_left_uncovered():
    result = _tools().run("check", {"directives": [{
        "source_id": "source-1", "action": "required_assignment", "employee": "רון",
        "date": SUNDAY, "shift": NIGHT, "reason": "חובה"}]})
    assert not result["ok"]
    assert "not eligible" in result["problems"][0]
    assert result["sources_not_covered"] == ["source-1"]


def test_dry_run_shows_what_a_hard_request_would_leave_short():
    everyone_but_dana = [_avoid(name, weekdays=[], dates=[SUNDAY], is_hard=True)
                         for name in ("דניאל", "יוסי")]
    hard_dana = _avoid("דנה", weekdays=[], dates=[SUNDAY], is_hard=True)
    result = _tools().run("dry_run", {"requests": everyone_but_dana + [hard_dana]})
    assert not result["ok"] and result["warnings"]


def test_an_unknown_tool_is_a_result_not_an_exception():
    assert _tools().run("delete_everything", {}) == {
        "tool": "delete_everything", "ok": False, "error": "unknown tool"}


def test_auto_reports_the_agents_calls_and_steps():
    llm = _ScriptedLlm([
        _turn(calls=[{"tool": "employee_state", "arguments": {"name": "דניאל"}}]),
        _turn(requests=[_avoid("דניאל")]),
    ])
    profile = _profile()
    result = Scheduler(llm).generate_span(
        profile, SUNDAY, SATURDAY, instructions="עדיף שדניאל לא יעבוד בלילות שני", engine="auto",
    )
    assert result["metrics"]["engine"] == "hybrid"
    assert result["metrics"]["model_calls"] == 2
    assert result["metrics"]["translation_steps"] == ["employee_state"]
    monday_night = [row["employee"] for row in result["assignments"]
                    if row["date"] == "2026-08-17" and row["shift"] == NIGHT]
    # Without the request, Monday night goes to דניאל.
    assert monday_night and monday_night != ["דניאל"]
