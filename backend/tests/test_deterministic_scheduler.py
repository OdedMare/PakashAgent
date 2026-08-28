"""The central scheduler is code: fast, repeatable and rotation-safe."""

import pytest

from app.bl.changes import ChangeAgent, OP_GENERATE_DAY
from app.bl.deterministic_scheduler import generate_day
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


class _UnavailableModel:
    def complete_json(self, *args, **kwargs):
        raise AssertionError("the Friday/Saturday command must not call a model")


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
