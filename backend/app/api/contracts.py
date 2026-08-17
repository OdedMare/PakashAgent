"""Pydantic HTTP contracts. No business logic — shapes only."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.common.runtime_settings.normalizers import MASKED_SECRET


class AnswerRequest(BaseModel):
    """One answer from the boss.

    A selected option and free text arrive on the same field: the model is
    told to treat a bare number as ambiguous rather than a choice
    (bl/prompts/interview.md), so the UI sends the option's *label*, not its
    index. Sending "2" would be exactly the ambiguity the prompt guards.
    """

    content: str = Field(min_length=1, max_length=4000)


class Option(BaseModel):
    id: str
    label: str
    recommended: bool


class Message(BaseModel):
    role: str
    content: str
    options: List[Option] = []
    recommendation: Optional[str] = None


class InterviewTurn(BaseModel):
    session_id: str
    status: str
    question_id: Optional[str] = None
    question: Optional[str] = None
    recommendation: Optional[str] = None
    options: List[Option] = []
    allow_free_text: bool = False
    turns: List[Message] = []
    profile: Optional[Dict[str, Any]] = None


class ModelsProbeRequest(BaseModel):
    """Unsaved LLM connection settings used to probe available models.

    Empty, omitted, or masked means "use the saved value", so the panel can
    check a typed base URL without the boss re-entering a stored API key.
    """

    llm_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None

    def override(self, name: str) -> Optional[str]:
        value = (getattr(self, name) or "").strip()
        return None if not value or value == MASKED_SECRET else value
