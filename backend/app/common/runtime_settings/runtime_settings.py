from dataclasses import dataclass
from typing import Optional


@dataclass
class RuntimeSettings:
    """The live settings every caller reads. Mutated by the store, never by
    callers — `dal/llm/` re-reads it on every call so a UI save takes effect
    without a restart."""

    database_url: str
    database_user: str
    database_password: str
    database_host: str
    database_port: Optional[int]
    database_name: str
    database_schema: str
    llm_model: str
    llm_diet_mode: bool
    llm_repetition_penalty: float
    llm_timeout_seconds: int
    llm_max_concurrency: int
    llm_base_url: Optional[str]
    openai_api_key: str
    # Per-role model ids and optional endpoints. Empty means "unset": models
    # fall back to `llm_model` and endpoints to `llm_base_url`, so existing
    # single-model deployments behave exactly as they did before these fields.
    llm_model_fast: str = ""
    llm_model_default: str = ""
    llm_model_advanced: str = ""
    llm_base_url_fast: Optional[str] = None
    llm_base_url_default: Optional[str] = None
    llm_base_url_advanced: Optional[str] = None
    # A role's endpoint may belong to a different provider than the general
    # one, so each carries its own credential. Empty falls back to
    # `openai_api_key`, keeping single-provider deployments unchanged.
    llm_api_key_fast: str = ""
    llm_api_key_default: str = ""
    llm_api_key_advanced: str = ""
    llm_queue_seconds: int = 180
    # Model calls one team may have in flight at once; 0 = `llm_max_concurrency`.
    llm_team_concurrency: int = 0
    # False accepts any TLS certificate from the model server. See
    # `Settings.llm_verify_ssl` for why this is a last resort.
    llm_verify_ssl: bool = True
    # The constraint solver (`bl/solver/`): wall time per solve and its
    # parallel workers. Read per build, so a saved change applies next time.
    solver_time_limit_seconds: float = 10.0
    solver_workers: int = 8
