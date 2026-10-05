"""One conversational turn of the intro interview.

Ported from the `plan-chat` planners in AiSummryIO: the model interviews the
manager one question per turn, each question carrying a recommended answer and
clickable options, and every turn returns the draft profile so far so the
summary fills in as the interview proceeds.

The interview never acts on its own conclusion. A turn that still asks
something — or that is only now presenting its summary for approval — is not
ready, and `turn.is_ready` enforces that rather than trusting the prompt to.

This package stays a pure function of the conversation. `interview_service`
owns the session and replays the history on every turn, which is what lets
this be tested against a fake model with no database.

| Module | Owns |
|---|---|
| `intro.py` | `IntroInterview`: payload, model call |
| `turn.py` | Shaping one model answer; the `ready` gate |
| `flow.py` | Keeping the interview on its core topics |
| `topics.py` | The nine topics; recognising a repeated question |
| `draft.py` | Merging the draft; what it still owes |
| `schema.py`, `profile_schema.py` | The response and profile schemas |
| `history.py` | The conversation as the model reads it back |
"""

from app.bl.interview.draft import empty_draft, missing_topics
from app.bl.interview.intro import IntroInterview
from app.bl.interview.schema import INTERVIEW_RESPONSE_SCHEMA
from app.bl.interview.topics import (
    CONTINUE_ANSWER,
    CONTINUE_TOPIC_ID,
    CORE_TOPIC_IDS,
    FINISH_ANSWER,
    INTERVIEW_TOPICS,
)

__all__ = [
    "CONTINUE_ANSWER", "CONTINUE_TOPIC_ID", "CORE_TOPIC_IDS", "FINISH_ANSWER",
    "INTERVIEW_RESPONSE_SCHEMA", "INTERVIEW_TOPICS", "IntroInterview",
    "empty_draft", "missing_topics",
]
