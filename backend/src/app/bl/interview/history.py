"""The conversation as the model reads it back."""

from typing import Dict, List

from app.bl.interview.text import MAX_MESSAGE_CHARS
from app.common.errors import AgentError

# The interview is bounded at roughly the topic count, so history is not
# windowed for a context budget — this is a guard against a pathological
# session, not a summarization strategy.
_MAX_MESSAGES = 200
# The questions already put to the manager, listed separately from the
# transcript so the instruction not to repeat one has something exact to
# point at.
_MAX_ASKED = 40


def validated_history(history) -> List[Dict[str, str]]:
    """The conversation, bounded, with only the two roles the prompt names.

    An empty message is dropped rather than rejected: the manager's own blank
    submission is refused a layer up, so anything empty here came out of the
    store. Raising instead would wedge the session permanently, since the same
    row is replayed on every later turn and would fail identically each time.
    """
    if not isinstance(history, list):
        raise AgentError("היסטוריית הראיון אינה תקינה")
    clean = []
    for message in history:
        if not isinstance(message, dict):
            raise AgentError("הודעה בראיון אינה תקינה")
        role, content = message.get("role"), message.get("content")
        if role not in ("assistant", "user") or not isinstance(content, str):
            raise AgentError("הודעה בראיון אינה תקינה")
        content = content.strip()
        if content:
            clean.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    return clean[-_MAX_MESSAGES:]


def asked_questions(history: List[Dict[str, str]]) -> List[str]:
    """Every question already put to the manager, oldest first.

    Read off the assistant turns rather than kept as separate state, so it
    cannot drift from the thread the manager actually saw. A question
    answered vaguely settles nothing and never reaches `resolved`, which is
    exactly the question a model working from settled facts will ask again.
    """
    asked = [
        message["content"] for message in history
        if message["role"] == "assistant"
    ]
    return asked[-_MAX_ASKED:]
