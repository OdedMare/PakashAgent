"""Environment defaults; RuntimeSettingsStore applies UI overrides."""

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
    """Model for short, lightweight work. No flow is routed here since the
    briefing was removed; kept so a saved setting still loads. Empty = use
    `llm_model`."""

    llm_model_default: str = ""
    """Model for conversation-shaped work — the manager chat (`planner`),
    `changes`, `learn` — and for any call naming no role. Empty = use
    `llm_model`."""

    llm_model_advanced: str = ""
    """Model for a build's translation of the manager's sentences (the
    `scheduler` flow, `bl/directive_agent/`). Empty = use `llm_model`."""

    llm_base_url_fast: Optional[str] = None
    """Endpoint for the fast role. Empty = use `llm_base_url`."""

    llm_base_url_default: Optional[str] = None
    """Endpoint for the default role. Empty = use `llm_base_url`."""

    llm_base_url_advanced: Optional[str] = None
    """Endpoint for the advanced role. Empty = use `llm_base_url`."""

    llm_api_key_fast: str = ""
    """API key for the fast role's endpoint. Empty = use `openai_api_key`."""

    llm_api_key_default: str = ""
    """API key for the default role's endpoint. Empty = use
    `openai_api_key`."""

    llm_api_key_advanced: str = ""
    """API key for the advanced role's endpoint. Empty = use
    `openai_api_key`.

    A role pointing at a different provider needs a different credential:
    the moment `llm_base_url_advanced` names a hosted API while the general
    endpoint is a local Ollama, the shared key is either absent or belongs to
    the wrong service. So each endpoint field has a key field beside it, and
    a key travels with the URL it authenticates rather than with the process.
    """

    llm_diet_mode: bool = False
    """Use compact prompts and bounded completion output."""

    llm_verify_ssl: bool = True
    """Verify the model server's TLS certificate. Applies to every LLM
    connection — completions and the `/models` probe alike.

    Turning it off is for an internal server whose certificate is self-signed
    or issued by a CA the process does not trust. It silences the error by
    accepting *any* certificate, so the API key and every prompt travel over
    a connection anyone in the path can intercept. Pointing `SSL_CERT_FILE`
    at the right CA bundle is the fix that keeps verification on."""

    llm_timeout_seconds: int = 0
    """Maximum wall time for ONE HTTP completion to the model.
    **0 — the default — means the built-in ceiling: 300s for chat and every
    other flow, 900s for a build's translation** (`dal/llm/budgets.py`).

    It used to mean no limit at all, and then one call the server never answered held
    its worker and model slot until a restart, and every later chat message
    and build waited on "ממתין למודל…" behind it. A stuck call now fails with
    a Hebrew error and gives its slot back; a read timeout is not retried.

    Not a budget for the whole logical call: the degradation ladder and the
    parse retry above it each get their own, derived from this one.

    **Why a ceiling rather than a guess.** Every finite value shipped here
    was wrong for somebody: 120s failed a large model on constrained
    hardware *while the server was still generating*. So the default is the
    generous built-in ceiling, which only catches a server that is hung
    rather than slow (D38). A model genuinely slower than five minutes per
    chat answer needs this raised; set it comfortably above the slowest real
    answer, not to a round number that feels safe."""

    llm_queue_seconds: int = 0
    """Maximum time interactive work may wait for a model slot.

    This bounds only the queue, where no answer is being generated yet.
    **0 — the default — removes the queue limit**, just like the model-call
    timeout above. Set a positive value only when interactive work should
    deliberately give up while another generation owns the model slot."""

    # A hosted API or a batching server (vLLM, TGI) takes several at once;
    # a one-at-a-time local Ollama should lower this to 1.
    llm_max_concurrency: int = 4
    """How many HTTP completions may be in flight across API and workers.

    PostgreSQL advisory locks coordinate every process and read this setting
    on acquisition, so a saved change applies to the next model call.

    A team may occupy all of them unless `llm_team_concurrency` says
    otherwise. The right global
    number depends entirely on what is serving the model. A server
    that batches continuously — vLLM, TGI — does its own scheduling and is
    *starved* by a low limit here, because requests this process is holding
    back are requests it cannot put in a batch; 16 or more suits those. A
    server that processes one request at a time, which is Ollama's default,
    is only thrashed by concurrency, and 1-2 keeps latency honest. 4 is the
    middle that assumes neither.
    """

    llm_reasoning_effort: str = ""
    """How long a reasoning model thinks before it answers: `off`, `low`,
    `medium` or `high`. Empty — the default — sends nothing, because a model
    that does not reason rejects the field.

    Thinking is most of the wait. gpt-oss reasons at `medium` unless told
    otherwise (sent as `reasoning_effort`; it cannot stop, so `off` is
    `low`). Qwen3 thinks unless its chat template says otherwise (`off` and
    `low` send `enable_thinking: false`). Reading a rule or a request is not
    a hard problem; raise it only when the faster setting starts to misread
    them."""

    llm_team_concurrency: int = 0
    """How many of those calls one team may hold at once. **0 — the default —
    means all of them.** It was one, so a team's chat waited behind its own
    build's translation and one hung call stopped the whole team. Set a
    positive number on a deployment shared by several busy teams to keep one
    from occupying every slot."""

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

    solver_time_limit_seconds: float = 10.0
    """Wall time one solve may take (`bl/solver/`). The solver returns the
    best schedule found when the limit is reached; small teams are proven
    optimal well before it."""

    solver_workers: int = 8
    """Parallel search workers for one solve: more finds a better schedule
    in the same time. Among equally good schedules the pick may differ
    from one build to the next."""

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

    settings_password: str = "010802"
    """Password the settings panel asks for, on top of the boss session.

    The settings are process-wide -- model endpoints, API keys, the database
    URL -- while a boss session only proves ownership of one workspace. So
    editing them needs this as well. The default is committed so the panel
    opens out of the box; override it with `PAKASH_SETTINGS_PASSWORD` in any
    real deployment. Set to empty, the panel stays locked."""

    admin_password: str = ""
    """Password of the צוות משמרות זהב operator console (`/admin`, D28).

    Empty -- the default -- means "the same as `settings_password`": the
    operator is the one person who already holds that password, and the
    console is where the settings now live too. Set it to give the console a
    credential of its own. If both are empty the console stays locked."""

    admin_session_hours: int = 12
    """How long an operator stays signed in. Short, because that session can
    delete every workspace on the server."""

    open_signup: bool = False
    """Whether anyone may open a workspace from the login page. Off by
    default: teams are opened by the operator (D28). Turn on only for an
    install that genuinely wants self-service teams."""

    runtime_settings_file: str = "runtime-settings.json"
