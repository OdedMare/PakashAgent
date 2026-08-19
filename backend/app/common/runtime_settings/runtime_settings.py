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
