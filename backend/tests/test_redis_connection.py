"""Reaching Redis: the env's connection survives an earlier save."""

import json

from app.common import redis_hub
from app.common.config import Settings
from app.common.runtime_settings.runtime_settings_store import (
    RuntimeSettingsStore,
)

ENV_URL = "redis://cache.internal:6380/1"


def _env(tmp_path, **values):
    return Settings(
        _env_file=None, runtime_settings_file=str(tmp_path / "s.json"), **values,
    )


def test_a_save_made_before_redis_was_set_does_not_hide_the_env_s(tmp_path):
    # Saving the model with no Redis in env wrote an empty URL to the file.
    RuntimeSettingsStore(_env(tmp_path)).update({"llm_model": "other"})
    assert json.loads((tmp_path / "s.json").read_text())["redis_url"] == ""

    store = RuntimeSettingsStore(_env(
        tmp_path, redis_url=ENV_URL, redis_password="pw", redis_username="app",
    ))
    saved = store.get()
    assert saved.llm_model == "other"
    assert (saved.redis_url, saved.redis_username, saved.redis_password) == (
        ENV_URL, "app", "pw",
    )


def test_a_shared_save_with_no_redis_does_not_hide_the_env_s(tmp_path):
    store = RuntimeSettingsStore(_env(tmp_path, redis_host="cache.internal"))
    store._apply({"redis_url": "", "redis_host": "", "llm_model": "x"}, False)
    assert redis_hub.url_of(store.get()) == "redis://cache.internal:6379"


def test_a_redis_saved_in_the_panel_beats_the_env_s(tmp_path):
    store = RuntimeSettingsStore(_env(tmp_path, redis_url=ENV_URL))
    store.update({"redis_url": "redis://panel:6379/0"})
    reopened = RuntimeSettingsStore(_env(tmp_path, redis_url=ENV_URL))
    assert reopened.get().redis_url == "redis://panel:6379/0"
