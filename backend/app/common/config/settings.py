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
    """The model id. Default targets a local Ollama tag.

    Still the model every flow uses unless a role below names another one,
    and the fallback for every role that does not."""

    llm_model_fast: str = ""
    """Model for short, lightweight work (the briefing). Empty = use
    `llm_model`."""

    llm_model_default: str = ""
    """Model for conversation-shaped work — interview, changes, planner,
    learn — and for any call naming no role. Empty = use `llm_model`."""

    llm_model_advanced: str = ""
    """Model for schedule generation and other heavy reasoning. Empty = use
    `llm_model`."""

    llm_base_url_fast: Optional[str] = None
    """Endpoint for the fast role. Empty = use `llm_base_url`."""

    llm_base_url_default: Optional[str] = None
    """Endpoint for the default role. Empty = use `llm_base_url`."""

    llm_base_url_advanced: Optional[str] = None
    """Endpoint for the advanced role. Empty = use `llm_base_url`."""

    llm_diet_mode: bool = False
    """Use compact prompts and bounded completion output."""

    llm_timeout_seconds: int = 0
    """Maximum wall time for ONE HTTP completion to the model.
    **0 — the default — means no limit: wait for as long as the server takes.**

    Not a budget for the whole logical call: the degradation ladder and the
    parse retry above it each get their own, derived from this one. Set to 0,
    those go away with it.

    **Why the default is no timeout.** Every finite value shipped here was
    wrong for somebody. 120s was sized for a small local model answering in
    seconds; against a large model on constrained hardware it failed every
    call *while the server was still generating* — the answer arrived to a
    client that had already hung up, so a merely slow model looked broken.
    Raising it only moved the cliff, because the right number is a property
    of the model and the hardware, which this code cannot know.

    A ceiling below the real answer time is not a safety net; it is a
    guarantee of failure. So the backend no longer guesses one: generation is
    a background job checkpointed per day, the browser polls rather than
    holding the connection open, and **giving up is the UI's decision** — it
    is the only participant that knows whether anyone is still waiting.

    **What this gives up.** A server that is genuinely hung — not slow — now
    holds its worker thread until the process restarts, and with
    `llm_max_concurrency` at 1 that blocks every other model call. Set a
    positive value here if that ever happens; it should be comfortably above
    the slowest real answer, not a round number that feels safe."""

    # The shipped endpoint is Ollama, which serves one generation at a time.
    # vLLM/TGI deployments should raise this explicitly for batching.
    llm_max_concurrency: int = 1
    """How many HTTP completions may be in flight at once, process-wide.

    Env-only rather than a live runtime setting: the semaphore is built once
    at import, so a value saved in the UI could not resize it and would read
    as a control that does nothing.

    The right number depends entirely on what is serving the model. A server
    that batches continuously — vLLM, TGI — does its own scheduling and is
    *starved* by a low limit here, because requests this process is holding
    back are requests it cannot put in a batch; 16 or more suits those. A
    server that processes one request at a time, which is Ollama's default,
    is only thrashed by concurrency, and 1-2 keeps latency honest. 4 is the
    middle that assumes neither.
    """

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
