"""The settings HTTP boundary: masking, partial saves, and the model probe."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import settings as settings_router
from app.common.config.settings import Settings
from app.common.errors import AgentError, AppError
from app.common.runtime_settings.normalizers import MASKED_SECRET
from app.common.runtime_settings.runtime_settings_store import (
    RuntimeSettingsStore,
)


class FakeLLM:
    """Stands in for `OpenAIJsonClient`, recording how it was probed."""

    def __init__(self, models=None, error=None):
        self.models = models or ["gemma3:27b", "gemma3:12b"]
        self.error = error
        self.calls = []

    def list_models(self, base_url_override=None, api_key_override=None):
        self.calls.append((base_url_override, api_key_override))
        if self.error:
            raise self.error
        return self.models


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    env = Settings(
        _env_file=None,
        runtime_settings_file=str(tmp_path / "runtime-settings.json"),
    )
    return RuntimeSettingsStore(env)


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def client(store, llm):
    app = FastAPI()
    app.include_router(settings_router.build_router(store, llm))

    @app.exception_handler(AppError)
    async def handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc)}
        )

    return TestClient(app, raise_server_exceptions=False)


def test_get_returns_settings_with_secrets_masked(client, store):
    store.update({"openai_api_key": "sk-real-secret"})

    body = client.get("/api/settings").json()

    assert body["llm_model"] == "gemma3:27b"
    assert body["openai_api_key"] == MASKED_SECRET
    assert "sk-real-secret" not in str(body)


def test_unset_secret_is_empty_not_masked(client):
    """An empty mask would make the panel show "(saved)" for nothing."""
    assert client.get("/api/settings").json()["database_password"] == ""


def test_put_applies_a_partial_patch(client, store):
    body = client.put(
        "/api/settings", json={"llm_model": "gemma3:12b"}
    ).json()

    assert body["llm_model"] == "gemma3:12b"
    # Untouched fields survive a partial save.
    assert store.get().llm_base_url == "http://localhost:11434/v1"


def test_returned_mask_does_not_overwrite_the_stored_secret(client, store):
    store.update({"openai_api_key": "sk-real-secret"})

    client.put("/api/settings", json={"openai_api_key": MASKED_SECRET})

    assert store.get().openai_api_key == "sk-real-secret"


def test_invalid_value_is_a_400_carrying_the_reason(client):
    response = client.put("/api/settings", json={"database_schema": "no-dashes!"})

    assert response.status_code == 400
    assert "database_schema" in response.json()["detail"]


def test_a_rejected_patch_changes_nothing(client, store):
    """All of it or none of it — otherwise the live settings and the file on
    disk disagree until the next restart."""
    before = store.get().llm_model

    client.put("/api/settings", json={
        "llm_model": "should-not-stick",
        "database_schema": "no-dashes!",
    })

    assert store.get().llm_model == before


def test_saved_settings_survive_a_restart(client, store, tmp_path):
    client.put("/api/settings", json={"llm_model": "gemma3:12b"})

    env = Settings(
        _env_file=None,
        runtime_settings_file=str(tmp_path / "runtime-settings.json"),
    )
    assert RuntimeSettingsStore(env).get().llm_model == "gemma3:12b"


def test_get_models_probes_the_saved_connection(client, llm):
    body = client.get("/api/models").json()

    assert body["models"] == ["gemma3:27b", "gemma3:12b"]
    # No overrides: the GET form always reads the stored connection.
    assert llm.calls == [(None, None)]


def test_post_models_probes_an_unsaved_connection(client, llm):
    client.post("/api/models", json={
        "llm_base_url": "http://elsewhere:11434/v1",
        "openai_api_key": "sk-typed",
    })

    assert llm.calls[-1] == ("http://elsewhere:11434/v1", "sk-typed")


def test_probe_falls_back_to_saved_values(client, llm):
    """Empty and masked both mean "use what is stored", so the panel can test
    a typed base URL without the boss re-entering a saved key."""
    client.post("/api/models", json={
        "llm_base_url": "  ",
        "openai_api_key": MASKED_SECRET,
    })

    assert llm.calls[-1] == (None, None)


def test_probe_failure_reaches_the_panel_as_hebrew(store):
    app = FastAPI()
    app.include_router(settings_router.build_router(
        store, FakeLLM(error=AgentError("לא ניתן לטעון מודלים: refused")),
    ))

    @app.exception_handler(AppError)
    async def handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=exc.status_code, content={"detail": str(exc)}
        )

    response = TestClient(app, raise_server_exceptions=False).get("/api/models")

    assert response.status_code == 502
    assert "לא ניתן לטעון מודלים" in response.json()["detail"]
