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
    # How wide one scheduling model call is: "day" or "week". Read by
    # `bl/schedule_service.py` when a period is opened, so a saved change
    # applies to the next build without a restart. See
    # `Settings.schedule_generation_mode` for the tradeoff.
    schedule_generation_mode: str = "day"
