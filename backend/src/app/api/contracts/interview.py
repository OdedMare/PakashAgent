"""The intro interview's turns."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AnswerRequest(BaseModel):
    """One answer from the boss.

    A clicked option and free text arrive on the same field: an option's
    `answer` is a full sentence, sent verbatim as the boss's own message, so
    the model reads a click and a typed reply identically. That is why the UI
    sends `answer` and never a label or an index — a bare "2" would be the
    ambiguity the prompt explicitly guards against.
    """

    content: str = Field(min_length=1, max_length=4000)
    mode: Literal["answer", "correction"] = "answer"


class InterviewSeed(BaseModel):
    """Facts read from an existing schedule before the interview starts."""

    workplace_name: str = Field(default="", max_length=120)
    source_files: List[str] = Field(default=[], max_length=100)
    employees: Dict[str, List[str]] = {}
    shifts: Dict[str, List[str]] = {}
    starts_on: str = Field(default="", max_length=10)
    ends_on: str = Field(default="", max_length=10)


class Option(BaseModel):
    """A clickable answer. `label` captions the button, `answer` is sent."""

    label: str
    answer: str


class Question(BaseModel):
    """The single question a turn asks, with the agent's own recommendation."""

    topic_id: str = ""
    question: str
    recommendation: str = ""
    why: str = ""
    options: List[Option] = []


class Message(BaseModel):
    """One turn in the thread as the UI replays it.

    `options` and `recommendation` are lifted out of `question` so a past
    assistant turn can re-render its buttons without the client reaching
    into a nested object that is null on half the rows.
    """

    role: str
    content: str
    question: Optional[Question] = None
    options: List[Option] = []
    recommendation: Optional[str] = None
    mode: str = ""


class InterviewTurn(BaseModel):
    """One conversational turn, shaped like the reference `plan-chat` reply.

    `draft` is the profile so far and is present on every turn, so the
    summary panel fills in as the interview proceeds. `profile` stays null
    until the interview is confirmed complete — it is the durable result,
    while `draft` is a proposal that may still change.
    """

    session_id: str
    status: str
    reply: str = ""
    question: Optional[Question] = None
    resolved: List[str] = []
    open_points: List[str] = []
    awaiting_confirmation: bool = False
    ready: bool = False
    draft: Optional[Dict[str, Any]] = None
    turns: List[Message] = []
    profile: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
