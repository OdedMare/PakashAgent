"""Pydantic HTTP contracts. No business logic — shapes only."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.common.runtime_settings.normalizers import MASKED_SECRET


class AnswerRequest(BaseModel):
    """One answer from the boss.

    A clicked option and free text arrive on the same field: an option's
    `answer` is a full sentence, sent verbatim as the boss's own message, so
    the model reads a click and a typed reply identically. That is why the UI
    sends `answer` and never a label or an index — a bare "2" would be the
    ambiguity the prompt explicitly guards against.
    """

    content: str = Field(min_length=1, max_length=4000)


class Option(BaseModel):
    """A clickable answer. `label` captions the button, `answer` is sent."""

    label: str
    answer: str


class Question(BaseModel):
    """The single question a turn asks, with the agent's own recommendation."""

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


class CreateTeamRequest(BaseModel):
    """A new workspace. The password bound here is the boss's."""

    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=6, max_length=200)


class LoginRequest(BaseModel):
    team_id: str = Field(min_length=1)
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeRequest(BaseModel):
    current: str = Field(min_length=1, max_length=200)
    replacement: str = Field(min_length=6, max_length=200)


class TeamSummary(BaseModel):
    """A team as the unauthenticated login picker sees it."""

    id: str
    name: str


class Workspace(BaseModel):
    """The signed-in workspace.

    `member_token` is present for a boss (it is the link they hand out) and
    None for a member, who has no reason to re-read the credential they
    arrived on.
    """

    id: str
    name: str
    role: str
    member_token: Optional[str] = None
    claimed_sessions: Optional[int] = None


class TeamView(Workspace):
    """A workspace plus the workplace profile its interview produced."""

    profile: Optional[Dict[str, Any]] = None
