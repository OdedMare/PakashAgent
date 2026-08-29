"""The central scheduler is code: fast, repeatable and rotation-safe."""

import pytest

from app.bl.changes import ChangeAgent, OP_GENERATE_DAY
from app.bl.deterministic_scheduler import generate_day, generate_day_candidates
from app.common.errors import AgentError


SHIFT = "בוקר"


def _profile():
    return {
        "workplace": {
            "name": "יחידה",
            "round_first_closure_date": "2026-08-29",
            "round_first_closure_group": "א",
            "triplet_first_closure_date": "2026-08-29",
            "triplet_first_closure_group": "ג",
        },
        "employees": [
            {
                "name": "סבב א", "exit_pattern": "round",
                "rotation_group": "א", "eligible_shifts": [SHIFT],
                "is_shift_manager": True,
            },
            {
                "name": "סבב ב", "exit_pattern": "round",
                "rotation_group": "ב", "eligible_shifts": [SHIFT],
                "is_shift_manager": True,
            },
            {
                "name": "תלתון ג", "exit_pattern": "triplet",
                "rotation_group": "ג", "eligible_shifts": [SHIFT],
            },
            {
                "name": "תלתון א", "exit_pattern": "triplet",
                "rotation_group": "א", "eligible_shifts": [SHIFT],
            },
        ],
        "shifts": [{
            "name": SHIFT,
            "start_time": "07:00",
            "end_time": "15:00",
            "days": [],
            "requires_shift_manager": True,
            "staffing": [{
                "days": [], "headcount": 2, "required_roles": [],
            }],
        }],
    }


def test_saturday_uses_the_round_and_triplet_groups_that_close_it():
    result = generate_day(_profile(), "2026-08-29")

    assert [row["employee"] for row in result["assignments"]] == [
        "סבב א", "תלתון ג",
    ]
    assert result["metrics"]["engine"] == "deterministic"
    assert result["metrics"]["total_tokens"] == 0
    assert result["warnings"] == []


def test_declared_rotation_without_an_anchor_blocks_generation():
    profile = _profile()
    profile["workplace"]["triplet_first_closure_date"] = ""

    with pytest.raises(AgentError, match="תלתון"):
        generate_day(profile, "2026-08-29")


def test_agent_options_include_an_audited_exception_not_a_silent_override():
    profile = _profile()
    unavailable = [
        {
            "employee": row["name"], "date": "2026-08-29",
            "shift": SHIFT, "available": False, "is_hard": True,
            "reason": "לא זמין",
        }
        for row in profile["employees"]
    ]

    candidates = generate_day_candidates(
        profile, "2026-08-29", availability=unavailable, count=2,
        include_warning_candidate=True,
    )

    assert candidates[0]["assignments"] == []
    assert candidates[1]["assignments"]
    assert {warning["code"] for warning in candidates[1]["warnings"]} >= {
        "unavailable",
    }


class _UnavailableModel:
    def complete_json(self, *args, **kwargs):
        raise AssertionError("the Friday/Saturday command must not call a model")


class _DecisionModel:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def run_agent(self, *, tools, output_type, max_turns, **kwargs):
        self.calls += 1
        self.max_turns = max_turns
        available = {tool.name: tool for tool in tools}
        for call in self.answer.get("tool_calls", []):
            tool = available.get(call.get("tool"))
            if tool:
                arguments = call.get("arguments") or {}
                if "index" in call:
                    arguments = {"index": call["index"]}
                tool.invoke(arguments)
        if not self.answer.get("done"):
            raise AgentError("הסוכן לא השלים החלטת שיבוץ בזמן")
        return output_type(
            candidate=self.answer.get("candidate"),
            reply=self.answer.get("reply", ""),
            agent_reason=self.answer.get("agent_reason", ""),
        )


def test_decision_agent_cannot_choose_a_candidate_it_did_not_inspect():
    model = _DecisionModel({
        "done": True, "candidate": 0, "reply": "בחרתי",
        "agent_reason": "נראה טוב", "tool_calls": [],
    })

    with pytest.raises(AgentError, match="בלי לבדוק"):
        ChangeAgent(model).decide_day(
            "תשבץ את שבת", "2026-08-29", "", lambda: [{
                "assignments": [], "warnings": [], "notes": [],
                "workload_hours": [],
            }]
        )


def test_decision_tool_loop_is_bounded():
    model = _DecisionModel({
        "done": False, "candidate": -1, "reply": "",
        "agent_reason": "", "tool_calls": [{
            "tool": "run_scheduler", "index": -1,
        }],
    })

    with pytest.raises(AgentError, match="בזמן"):
        ChangeAgent(model).decide_day(
            "תשבץ את שבת", "2026-08-29", "", lambda: [{
                "assignments": [], "warnings": [], "notes": [],
                "workload_hours": [],
            }]
        )
    assert model.calls == 1
    assert model.max_turns == 4


@pytest.mark.parametrize(
    ("command", "date"),
    [("תשבץ את שבת", "2026-08-29"), ("תשבץ את יום שישי", "2026-08-28")],
)
def test_agent_understands_day_generation_without_a_model(command, date):
    schedule = {
        "starts_on": "2026-08-23",
        "ends_on": "2026-08-29",
        "slots": [
            {"shift_name": SHIFT, "slot_date": "2026-08-28"},
            {"shift_name": SHIFT, "slot_date": "2026-08-29"},
        ],
        "assignments": [],
    }

    proposal = ChangeAgent(_UnavailableModel()).propose(
        _profile(), schedule, command
    )

    assert proposal["needs_reason"] is False
    assert proposal["operations"] == [{
        "action": OP_GENERATE_DAY,
        "employee": "",
        "shift": "",
        "date": date,
        "reason": "בקשת המנהל לבנות את היום",
    }]
