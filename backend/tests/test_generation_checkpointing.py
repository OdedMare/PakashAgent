"""Adaptive splitting persists each smaller span and resumes only unfinished dates."""

from app.common.errors.errors import AgentError, ModelOutputError
from tests.test_schedule_api import (
    MORNING, _DeferredLauncher, _FakeSettings, _build_app, _client, _generation,
)


def row(day):
    return dict(employee="דנה", shift=MORNING, date=day, reason="זמינה ומוסמכת לבוקר")


def test_failed_split_child_keeps_earlier_checkpoint_and_resumes_just_that_child():
    launcher = _DeferredLauncher()
    app, repo = _build_app([
        ModelOutputError("context overflow"), _generation([row("2026-10-05")]),
        AgentError("אין חיבור"), AgentError("אין חיבור"), AgentError("אין חיבור"),
        _generation([row("2026-10-06")]),
    ], launch=launcher, settings=_FakeSettings("week"))
    client = _client(app)
    started = client.post("/api/schedule/generate/start", json={
        "starts_on": "2026-10-05", "ends_on": "2026-10-06",
    }).json()
    path = "/api/schedule/generate/%s/run" % started["id"]
    client.post(path)
    launcher.run_next()
    failed = client.get("/api/schedule/%s" % started["id"]).json()
    assert failed["generation"]["status"] == "failed"
    assert failed["generation"]["completed_days"] == 1
    assert [(day["date"], day["status"]) for day in failed["generation"]["days"]] == [
        ("2026-10-05", "complete"), ("2026-10-06", "failed"),
    ]
    assert [assignment["date"] for assignment in failed["assignments"]] == ["2026-10-05"]
    assert failed["generation"]["days"][0]["metrics"]["model_calls"] == 2
    assert failed["generation"]["days"][1]["metrics"]["model_calls"] == 3
    client.post(path)
    launcher.run_next()
    finished = client.get("/api/schedule/%s" % started["id"]).json()
    assert finished["generation"]["completed_days"] == 2
    assert finished["generation"]["days"][0]["attempts"] == 1
    assert finished["generation"]["days"][1]["metrics"]["model_calls"] == 4
    assert len(repo.model_calls) == 6


def test_failed_repair_checkpoints_draft_and_remaining_warnings():
    launcher = _DeferredLauncher()
    app, _ = _build_app([_generation([]), AgentError("תיקון נכשל")], launch=launcher)
    client = _client(app)
    started = client.post("/api/schedule/generate/start", json={
        "starts_on": "2026-10-06", "ends_on": "2026-10-06",
    }).json()
    client.post("/api/schedule/generate/%s/run" % started["id"])
    launcher.run_next()
    finished = client.get("/api/schedule/%s" % started["id"]).json()
    assert finished["status"] == "draft"
    assert finished["generation"]["status"] == "complete"
    assert any(item["code"] == "unfilled" for item in finished["warnings"])
    assert finished["generation"]["days"][0]["metrics"]["repair_error"]
    assert any("הטיוטה" in note for note in finished["notes"])
