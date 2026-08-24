"""Settings store: env defaults, UI overrides, secret masking, normalization."""

import json
import os

import pytest

from app.common.config.settings import Settings
from app.common.runtime_settings.normalizers import MASKED_SECRET
from app.common.runtime_settings.runtime_settings_store import (
    RuntimeSettingsStore,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    # `_env_file=None` stops the .env file being read, but NOT the real
    # environment, and these tests assert on the declared defaults. A stray
    # OPENAI_API_KEY in the developer's shell, or the PAKASH_* the devsandbox
    # container sets, would otherwise change what the defaults are.
    for name in list(os.environ):
        if name.startswith("PAKASH_") or name == "OPENAI_API_KEY":
            monkeypatch.delenv(name, raising=False)
    env = Settings(
        _env_file=None,
        runtime_settings_file=str(tmp_path / "runtime-settings.json"),
    )
    return RuntimeSettingsStore(env)


def test_env_defaults_are_the_starting_point(store):
    settings = store.get()
    assert settings.llm_base_url == "http://localhost:11434/v1"
    # 0 means "no timeout": the UI decides when to stop waiting.
    assert settings.llm_timeout_seconds == 0
    # 0 means "do not send repetition_penalty at all".
    assert settings.llm_repetition_penalty == 0.0


def test_update_overrides_env_without_restart(store):
    store.update({"llm_model": "llama3.1:70b"})
    assert store.get().llm_model == "llama3.1:70b"


def test_saved_settings_survive_a_restart(tmp_path):
    path = str(tmp_path / "runtime-settings.json")
    first = RuntimeSettingsStore(
        Settings(_env_file=None, runtime_settings_file=path)
    )
    first.update({"llm_model": "saved-model"})

    reloaded = RuntimeSettingsStore(
        Settings(_env_file=None, runtime_settings_file=path)
    )
    assert reloaded.get().llm_model == "saved-model"


def test_public_masks_secrets_and_never_leaks_them(store):
    store.update({"openai_api_key": "sk-real-secret"})
    public = store.public()
    assert public["openai_api_key"] == MASKED_SECRET
    assert "sk-real-secret" not in json.dumps(public)


def test_public_reports_empty_secret_as_empty_not_masked(store):
    # An empty field must not look like a stored secret, or the UI would
    # show a mask for a key that was never set.
    assert store.public()["openai_api_key"] == ""


def test_masked_value_coming_back_keeps_the_stored_secret(store):
    store.update({"openai_api_key": "sk-real-secret"})
    # The UI round-trips the mask for a field the boss did not retype.
    store.update({"openai_api_key": MASKED_SECRET, "llm_model": "other"})
    assert store.get().openai_api_key == "sk-real-secret"
    assert store.get().llm_model == "other"


def test_pasted_endpoint_has_its_operation_suffix_stripped(store):
    # The SDK appends the path itself; leaving the suffix on 404s every call.
    store.update({"llm_base_url": "http://box:8000/v1/chat/completions"})
    assert store.get().llm_base_url == "http://box:8000/v1"


def test_emptied_base_url_clears_rather_than_keeping_the_old_one(store):
    store.update({"llm_base_url": ""})
    assert store.get().llm_base_url is None


def test_jdbc_url_is_accepted_and_sets_the_schema(store):
    store.update({
        "database_url": "jdbc:postgresql://host:5432/db?currentSchema=pakash",
    })
    settings = store.get()
    assert settings.database_url.startswith("postgresql://")
    # libpq rejects `currentSchema`; it must become an options payload.
    assert "currentSchema" not in settings.database_url
    assert "search_path" in settings.database_url
    assert settings.database_schema == "pakash"


def test_a_schema_name_that_could_reach_sql_is_rejected(store):
    # The schema is interpolated into SET search_path.
    with pytest.raises(ValueError):
        store.update({"database_schema": "pakash; DROP TABLE employees"})


def test_timeout_zero_is_kept_and_means_no_limit(store):
    """0 must survive the save. It used to be clamped to 1 on the grounds
    that "a 0 would make every completion time out instantly" — true of the
    SDK, which is why `dal/llm/` translates it, and exactly why clamping was
    wrong: it turned a request for NO ceiling into the harshest one there is.
    """
    store.update({"llm_timeout_seconds": 0})
    assert store.get().llm_timeout_seconds == 0


def test_a_negative_timeout_folds_to_no_limit(store):
    """Both mean "no ceiling" and there is nothing else a negative could
    mean, so it is folded rather than rejected."""
    store.update({"llm_timeout_seconds": -30})
    assert store.get().llm_timeout_seconds == 0


def test_concurrency_zero_is_still_clamped(store):
    """The exemption is for the timeout alone. A 0 here would mean a
    semaphore admitting nobody, which is not a setting anyone wants."""
    store.update({"llm_max_concurrency": 0})
    assert store.get().llm_max_concurrency == 1


def test_repetition_penalty_is_clamped_to_the_supported_range(store):
    store.update({"llm_repetition_penalty": 9.0})
    assert store.get().llm_repetition_penalty == 2.0


def test_a_bad_value_from_the_ui_is_rejected_loudly(store):
    with pytest.raises((TypeError, ValueError)):
        store.update({"llm_timeout_seconds": "not-a-number"})


def test_a_bad_value_in_a_saved_file_does_not_stop_startup(tmp_path):
    # An older or hand-edited file must not make the process unbootable.
    path = tmp_path / "runtime-settings.json"
    path.write_text(json.dumps({"llm_timeout_seconds": "nonsense"}), "utf-8")
    store = RuntimeSettingsStore(
        Settings(_env_file=None, runtime_settings_file=str(path))
    )
    assert store.get().llm_timeout_seconds == 0


def test_unknown_keys_in_a_patch_are_ignored(store):
    store.update({"not_a_setting": "x"})
    assert not hasattr(store.get(), "not_a_setting")


# --- per-role models -------------------------------------------------------

def test_role_models_start_unset_so_one_model_deployments_are_unchanged(store):
    settings = store.get()
    assert settings.llm_model_fast == ""
    assert settings.llm_model_default == ""
    assert settings.llm_model_advanced == ""
    assert settings.llm_base_url_fast is None
    assert settings.llm_base_url_default is None
    assert settings.llm_base_url_advanced is None


def test_role_models_are_saved_and_survive_a_restart(tmp_path):
    path = str(tmp_path / "runtime-settings.json")
    first = RuntimeSettingsStore(
        Settings(_env_file=None, runtime_settings_file=path)
    )
    first.update({
        "llm_model_fast": "small-model",
        "llm_model_default": "chat-model",
        "llm_model_advanced": "big-model",
        "llm_base_url_fast": "http://fast:8000/v1",
        "llm_base_url_default": "http://chat:8000/v1",
        "llm_base_url_advanced": "http://advanced:8000/v1",
    })

    reloaded = RuntimeSettingsStore(
        Settings(_env_file=None, runtime_settings_file=path)
    ).get()
    assert reloaded.llm_model_fast == "small-model"
    assert reloaded.llm_model_default == "chat-model"
    assert reloaded.llm_model_advanced == "big-model"
    assert reloaded.llm_base_url_fast == "http://fast:8000/v1"
    assert reloaded.llm_base_url_default == "http://chat:8000/v1"
    assert reloaded.llm_base_url_advanced == "http://advanced:8000/v1"


def test_a_settings_file_predating_roles_still_loads(tmp_path):
    """The backward-compatibility case: a file written before the role
    fields existed must load, keep its model, and leave the roles unset so
    every flow keeps using it."""
    path = tmp_path / "runtime-settings.json"
    path.write_text(json.dumps({"llm_model": "old-model"}), "utf-8")

    settings = RuntimeSettingsStore(
        Settings(_env_file=None, runtime_settings_file=str(path))
    ).get()
    assert settings.llm_model == "old-model"
    assert settings.llm_model_fast == ""
    assert settings.llm_model_advanced == ""
    assert settings.llm_base_url_advanced is None


def test_a_role_can_be_cleared_back_to_the_default_model(store):
    # Emptying a role must unset it, not keep the previous selection —
    # otherwise a chosen model could never be undone from the UI.
    store.update({"llm_model_advanced": "big-model"})
    store.update({"llm_model_advanced": ""})
    assert store.get().llm_model_advanced == ""


def test_a_role_url_is_normalized_and_can_be_cleared(store):
    store.update({
        "llm_base_url_advanced": "http://box:8000/v1/chat/completions",
    })
    assert store.get().llm_base_url_advanced == "http://box:8000/v1"

    store.update({"llm_base_url_advanced": ""})
    assert store.get().llm_base_url_advanced is None


def test_the_roles_never_carry_a_hardcoded_model_name(store):
    # Which models exist is the server's business. Anything shipped here as
    # a default would be a model this deployment may not serve.
    public = store.public()
    for field in (
        "llm_model_fast", "llm_model_default", "llm_model_advanced",
    ):
        assert public[field] == ""


def test_saving_a_role_model_leaves_the_stored_api_key_alone(store):
    # The panel round-trips the mask for a key the boss did not retype.
    store.update({"openai_api_key": "sk-real-secret"})
    store.update({
        "llm_model_advanced": "big-model",
        "openai_api_key": MASKED_SECRET,
    })
    assert store.get().openai_api_key == "sk-real-secret"
    assert store.get().llm_model_advanced == "big-model"
