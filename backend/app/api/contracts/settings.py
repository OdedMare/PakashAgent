"""Runtime-settings requests."""

from typing import Optional

from pydantic import BaseModel

from app.common.runtime_settings.normalizers import MASKED_SECRET


class ModelsProbeRequest(BaseModel):
    """Unsaved LLM connection settings used to probe available models.

    Empty, omitted, or masked means "use the saved value", so the panel can
    check a typed base URL without the boss re-entering a stored API key.

    `role` says which saved connection those omissions fall back to. With
    roles free to sit on different providers, the general endpoint's
    catalogue is the wrong list for a role pointing somewhere else — so the
    panel probes per role, and a role whose fields are both empty is probed
    through the same fallback the client itself would use.
    """

    llm_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    role: Optional[str] = None
    # The TLS switch as the form shows it, so turning verification off can be
    # tested before it is saved. Omitted means "use the saved value".
    llm_verify_ssl: Optional[bool] = None

    def override(self, name: str) -> Optional[str]:
        value = (getattr(self, name) or "").strip()
        return None if not value or value == MASKED_SECRET else value


class RedisProbeRequest(BaseModel):
    """A Redis connection typed into the form, tested before it is saved.

    Omitted means "the saved value". For the URL an empty string is a real
    answer -- "no Redis" -- so only `None` falls back; for the password
    empty or masked means the stored one, as with every other secret.
    """

    redis_url: Optional[str] = None
    # Same rule as the URL: only `None` is "the saved value"; an empty host,
    # port or username typed in the form means "none", as it would on save.
    redis_host: Optional[str] = None
    redis_port: Optional[str] = None
    redis_username: Optional[str] = None
    redis_password: Optional[str] = None
    redis_key_prefix: Optional[str] = None

    def password(self) -> Optional[str]:
        value = self.redis_password or ""
        return None if not value or value == MASKED_SECRET else value
