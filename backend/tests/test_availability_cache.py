"""`effective_availability` is remembered, and each caller owns its copy."""

import json
import pathlib

from app.bl.scheduler import availability
from app.bl.scheduler.availability import effective_availability

SCENARIO = pathlib.Path(__file__).resolve().parents[2] / "devsandbox" / "scenarios" / "unit_619.json"


def _profile():
    return json.loads(SCENARIO.read_text(encoding="utf-8"))


def test_the_same_question_is_answered_once_and_identically(monkeypatch):
    calls = []
    real = availability._effective_availability
    monkeypatch.setattr(availability, "_effective_availability",
                        lambda *args: calls.append(args) or real(*args))
    profile = _profile()
    rows = [{"employee": profile["employees"][0]["name"], "date": "2026-11-10",
             "available": False, "is_hard": True}]

    first = effective_availability(profile, rows, "2026-11-08", "2026-11-14")
    again = effective_availability(_profile(), list(rows), "2026-11-08", "2026-11-14")

    assert first == again and len(calls) == 1
    assert any(row.get("rotation_group") for row in first)


def test_a_caller_editing_its_answer_does_not_change_the_next_one():
    profile = _profile()
    first = effective_availability(profile, [], "2026-11-01", "2026-11-07")
    first[0]["employee"] = "שונה"
    first.append({"employee": "נוסף"})

    again = effective_availability(profile, [], "2026-11-01", "2026-11-07")

    assert again[0]["employee"] != "שונה" and {"employee": "נוסף"} not in again


def test_a_changed_profile_is_not_answered_from_memory():
    profile = _profile()
    before = effective_availability(profile, [], "2026-11-01", "2026-11-07")
    profile["employees"][0]["inactive_from"] = "2026-11-01"

    after = effective_availability(profile, [], "2026-11-01", "2026-11-07")

    assert after != before
