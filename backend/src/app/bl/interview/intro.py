"""`IntroInterview`: ask the next question, return the profile drafted so far."""

import json
from typing import Dict, List, Optional

from app.bl.interview.flow import TopicFlow
from app.bl.interview.history import asked_questions, validated_history
from app.bl.interview.schema import INTERVIEW_RESPONSE_SCHEMA
from app.bl.interview.text import as_dict, bounded, lines
from app.bl.interview.topics import CORE_TOPIC_IDS, INTERVIEW_TOPICS
from app.bl.interview.turn import shape_turn
from app.bl.prompts import load
from app.common.errors import AgentError

# How much of the conversation the model reads back. The draft and the state
# lists carry the settled *facts*, but neither records which questions were
# already put; a model handed only the last exchange re-asks, and the
# interview circles instead of advancing.
_RECENT_TURNS = 12


class IntroInterview:
    """The caller owns persistence and passes the conversation back on every
    turn, so this stays a pure function of the history plus the draft it is
    handed.
    """

    def __init__(self, llm):
        self._llm = llm

    def next_turn(
        self, history: List[Dict[str, str]], draft: Optional[dict] = None,
        state: Optional[dict] = None,
    ) -> dict:
        """One turn: gather context, ask the model once, shape the answer."""
        state = as_dict(state)
        payload = self._payload(validated_history(history), draft, state)
        result = shape_turn(self._ask(payload), draft)
        flow = TopicFlow(
            state,
            answered=payload["answered_topic_ids"],
            asked=payload["questions_already_asked"],
            optional_choice=payload["optional_interview_choice"],
        )
        return flow.steer(result)

    @staticmethod
    def _payload(clean: List[Dict[str, str]], draft, state: dict) -> dict:
        return {
            "topics": INTERVIEW_TOPICS,
            # The complete transcript stays in storage and in the UI; the
            # model gets the recent stretch, enough to see what it asked.
            "recent_conversation": clean[-_RECENT_TURNS:],
            # Every question asked so far, including ones scrolled out of the
            # window above. This is the anti-repetition list.
            "questions_already_asked": (
                lines(state.get("questions_already_asked"))
                or asked_questions(clean)
            ),
            "draft_so_far": as_dict(draft),
            "resolved_so_far": lines(state.get("resolved")),
            "open_points_so_far": lines(state.get("open_points")),
            "answered_topic_ids": [
                topic_id for topic_id in state.get("answered_topic_ids", [])
                if topic_id in CORE_TOPIC_IDS
            ],
            "optional_interview_choice": bounded(
                state.get("optional_interview_choice")
            ),
        }

    def _ask(self, payload: dict) -> dict:
        # Loaded per turn rather than at import, so editing the markdown
        # takes effect without a restart. The loader caches the read.
        answer = self._llm.complete_json(
            load("interview"),
            json.dumps(payload, ensure_ascii=False),
            schema=INTERVIEW_RESPONSE_SCHEMA,
            flow="interview",
        )
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר תוצאת ראיון לא תקינה")
        return answer
