"""Environment defaults; UI overrides are applied by RuntimeSettingsStore."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Env-derived DEFAULTS. Values the boss can edit in the UI live in
    common.runtime_settings (this feeds its initial values)."""

    model_config = SettingsConfigDict(
        env_prefix="PAKASH_", env_file=".env", extra="ignore"
    )

    database_url: str = "postgresql://pakash:pakash@localhost:5432/pakash"
    """Postgres holding the workplace profile, schedules, and the change log.
    A `jdbc:postgresql://...` URL is accepted and converted automatically."""

    database_user: str = "pakash"
    """Optional explicit Postgres user. Overrides credentials in the URL."""

    database_password: str = ""
    """Optional explicit Postgres password. Never returned by the API."""

    database_host: str = "localhost"
    """Optional explicit Postgres host. Overrides the host in the URL."""

    database_port: Optional[int] = 5432
    """Optional explicit Postgres port. Overrides the port in the URL."""

    database_name: str = "pakash"
    """Optional explicit database name. Overrides the database in the URL."""

    database_schema: str = "pakash"
    """PostgreSQL schema owning every table. Empty means the server default
    (normally `public`). Also settable as `?currentSchema=` in the URL."""

    llm_model: str = "gemma3:27b"
    """The model id. Default targets a local Ollama tag."""

    llm_diet_mode: bool = False
    """Use compact prompts and bounded completion output."""

    llm_timeout_seconds: int = 120
    """Maximum wall time for ONE HTTP completion to the model.

    Not a budget for the whole logical call: the degradation ladder and the
    parse retry above it each get their own, so a pathological call can take
    a multiple of this. It exists to stop a hung model server from holding a
    worker for the SDK's 600-second default."""

    llm_repetition_penalty: float = 0.0
    """Penalty applied to already-emitted tokens, discouraging loops.

    NOT a standard OpenAI field — it is a vLLM/Ollama/TGI extension, so it is
    sent inside `extra_body`. `0` means "do not send it at all" and is the
    default, because OpenAI itself rejects the unknown key; `1.0` is neutral
    on the servers that do implement it, and above that penalizes. Past ~1.2
    it starts to fight JSON mode, since the syntax a JSON object must repeat
    (braces, quotes, commas) is exactly what the penalty suppresses."""

    llm_base_url: Optional[str] = "http://localhost:11434/v1"
    """OpenAI-compatible endpoint. Default: local Ollama."""

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    """Read unprefixed, as the SDK expects. Empty is fine when a local
    `llm_base_url` is set — those servers ignore auth."""

    session_secret: str = ""
    """Key that signs the workspace session cookie.

    Empty means "generate one per process". That is the safe default for a
    single-machine dev run, and deliberately NOT safe for a deployment with
    more than one worker: each worker would sign with a different key and
    reject the others' cookies, so everyone would be logged out at random.
    Set `PAKASH_SESSION_SECRET` in production — and note that changing it
    logs every boss out, since their existing cookies stop verifying."""

    session_days: int = 30
    """How long a boss stays logged in before the cookie expires."""

    runtime_settings_file: str = "runtime-settings.json"
