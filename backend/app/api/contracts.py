"""Pydantic HTTP contracts. No business logic — shapes only."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
