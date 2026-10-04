"""Keeping the interview on its topics, whatever the model asked next.

The model chooses the order and the wording; code makes sure every core topic
gets a manager answer before optional discovery or a summary, that a
correction reopens the topic it corrects, and that the conversation never
stalls under no question at all.
"""

from typing import List

from app.bl.interview.draft import missing_topics
from app.bl.interview.text import as_dict, bounded
from app.bl.interview.topics import (
    CORE_TOPIC_IDS, already_asked, continue_question, next_topic_question,
    topic_question,
)

_CORE_DONE_REPLY = "סיימנו את תשע שאלות החובה."


class TopicFlow:
    def __init__(self, state: dict, answered: List[str], asked: List[str],
                 optional_choice: str):
        # Core topics are enforced only for sessions that track them.
        self._enforce = "answered_topic_ids" in state
        self._state = state
        self._asked = asked
        self._choice = optional_choice
        self._unanswered = [
            topic_id for topic_id in CORE_TOPIC_IDS if topic_id not in answered
        ]

    def steer(self, result: dict) -> dict:
        if not self._steer_core(result):
            self._avoid_repeat(result)
        self._never_stall(result)
        return result

    def _steer_core(self, result: dict) -> bool:
        """Apply the core-topic rules. True when one of them decided the turn."""
        if not self._enforce:
            return False
        correction = bounded(self._state.get("correction_topic_id"))
        if correction in self._unanswered:
            # A correction updates an earlier fact; it does not silently
            # answer the question that happened to be open at the time.
            return _ask(result, topic_question(correction))
        if self._unanswered:
            # The model may choose the order, but not skip a required topic
            # or jump straight to its summary.
            topic = as_dict(result.get("question")).get("topic_id")
            if topic not in self._unanswered:
                result["question"] = topic_question(self._unanswered[0])
            return _ask(result, result["question"])
        if not self._choice:
            result["reply"] = _CORE_DONE_REPLY
            return _ask(result, continue_question())
        if self._choice == "finish" and \
                not self._state.get("confirmation_was_awaiting"):
            result.update({
                "question": None, "awaiting_confirmation": True, "ready": False,
            })
            return True
        return False

    def _avoid_repeat(self, result: dict) -> None:
        question = result.get("question")
        if question is None or not already_asked(question["question"], self._asked):
            return
        replacement = next_topic_question(self._asked)
        if replacement is not None:
            result["question"] = replacement
        elif not missing_topics(result["draft"]):
            result.update({
                "question": None, "awaiting_confirmation": True, "ready": False,
            })

    def _never_stall(self, result: dict) -> None:
        """A turn with no question, not confirming and not done, stalls.

        A model can legally satisfy the schema with `question: null` while
        saying the interview is neither confirming nor done, leaving a live
        composer under no question. Keep it moving with the next topic.
        """
        if (
            result["question"] is None
            and not result["awaiting_confirmation"]
            and not result["ready"]
        ):
            result["question"] = next_topic_question(self._asked)


def _ask(result: dict, question: dict) -> bool:
    result.update({
        "question": question, "awaiting_confirmation": False, "ready": False,
    })
    return True
