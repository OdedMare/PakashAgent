"""Opik tracing is inert without a key and can never fail a model call (D30)."""

import sys
import types

import pytest

from app.common.config.settings import Settings
from app.dal.llm import tracing


@pytest.fixture(autouse=True)
def _reset_state():
    saved = dict(tracing._state)
    yield
    tracing._state.update(saved)


def test_no_key_leaves_tracing_off_and_everything_a_pass_through():
    assert tracing.init(Settings(_env_file=None, OPIK_API_KEY="")) is False
    client = object()
    assert tracing.wrap(client) is client
    with tracing.call("briefing", "fast", "m"):
        pass
    tracing.flush()


def test_a_broken_opik_never_fails_the_call(monkeypatch):
    broken = types.ModuleType("opik")

    def explode(*_args, **_kwargs):
        raise RuntimeError("opik is down")

    broken.start_as_current_trace = explode
    broken.flush_tracker = explode
    monkeypatch.setitem(sys.modules, "opik", broken)
    tracing._state.update(enabled=True, project="pakash")

    ran = []
    with tracing.call("scheduler", "advanced", "m"):
        ran.append(True)
    tracing.flush()
    assert ran == [True]


def test_an_error_inside_the_call_still_reaches_the_caller():
    with pytest.raises(ValueError):
        with tracing.call("changes", "default", "m"):
            raise ValueError("model said no")
