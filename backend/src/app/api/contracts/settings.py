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

    def override(self, name: str) -> Optional[str]:
        value = (getattr(self, name) or "").strip()
        return None if not value or value == MASKED_SECRET else value
