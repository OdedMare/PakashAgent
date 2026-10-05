"""What the stored turns of one interview say, read for the next model turn.

Questions live in the assistant turn payload, not in its reply, so everything
the model needs to move forward -- what it asked, which core topics have an
answer, whether the manager chose to continue -- is read off the stored rows
rather than kept as separate state that could drift from the thread.
"""

from typing import List

from app.bl.interview import (
    CONTINUE_ANSWER, CONTINUE_TOPIC_ID, CORE_TOPIC_IDS, FINISH_ANSWER,
)


def _payload(row: dict) -> dict:
    return row.get("payload") or {}


def _question(row: dict) -> dict:
    return _payload(row).get("question") or {}


def _is_correction(row: dict) -> bool:
    return _payload(row).get("mode") == "correction"


def stored_question(row: dict) -> str:
    """The exact question attached to one stored assistant turn."""
    value = _question(row).get("question")
    return value.strip() if isinstance(value, str) else ""


class TurnHistory:
    def __init__(self, turns: List[dict]):
        self._turns = list(turns or [])

    def replayed(self) -> List[dict]:
        """Every stored row as the model reads it back.

        Rows written before an empty `reply` was stored under its question are
        blank in `content` while still carrying that question in their
        payload, so the turn is recovered from there rather than replayed
        empty -- a turn that vanishes takes its question with it.
        """
        return [self._replay(row) for row in self._turns]

    @staticmethod
    def _replay(row: dict) -> dict:
        content = (row["content"] or "").strip()
        question = stored_question(row)
        if question and question not in content:
            content = "%s\nשאלה: %s" % (content, question) if content else question
        return {"role": row["role"], "content": content}

    def state_for_model(self, pending: dict) -> dict:
        """The pending state plus everything the stored turns imply."""
        state = dict(pending or {})
        state.update({
            "questions_already_asked": [
                question for row in self._turns if (question := stored_question(row))
            ],
            "answered_topic_ids": self.answered_topic_ids(),
            "optional_interview_choice": self.optional_interview_choice(),
            "confirmation_was_awaiting": self.last_assistant_was_awaiting(),
            "correction_topic_id": self.correction_topic_id(),
        })
        return state

    def answered_topic_ids(self) -> List[str]:
        """Core question ids that have a non-empty manager answer after them."""
        answered, open_topic = [], ""
        for row in self._turns:
            if row.get("role") == "assistant":
                topic_id = _question(row).get("topic_id")
                open_topic = topic_id if topic_id in CORE_TOPIC_IDS else ""
            elif (
                row.get("role") == "user" and open_topic
                and not _is_correction(row)
                and (row.get("content") or "").strip()
            ):
                if open_topic not in answered:
                    answered.append(open_topic)
                open_topic = ""
        return answered

    def optional_interview_choice(self) -> str:
        """The manager's answer to the deterministic continue-or-finish turn."""
        awaiting_choice = False
        for row in self._turns:
            if row.get("role") == "assistant":
                awaiting_choice = _question(row).get("topic_id") == CONTINUE_TOPIC_ID
            elif row.get("role") == "user" and awaiting_choice:
                if _is_correction(row):
                    continue
                answer = (row.get("content") or "").strip()
                if answer == CONTINUE_ANSWER:
                    return "continue"
                if answer == FINISH_ANSWER:
                    return "finish"
                awaiting_choice = False
        return ""

    def last_assistant_was_awaiting(self) -> bool:
        for row in reversed(self._turns):
            if row.get("role") == "assistant":
                return bool(_payload(row).get("awaiting_confirmation"))
        return False

    def correction_topic_id(self) -> str:
        """The question a trailing correction interrupted, if there is one."""
        if not self._turns:
            return ""
        last = self._turns[-1]
        if last.get("role") != "user" or not _is_correction(last):
            return ""
        for row in reversed(self._turns[:-1]):
            if row.get("role") == "assistant":
                topic_id = _question(row).get("topic_id")
                return topic_id if topic_id in CORE_TOPIC_IDS else ""
        return ""
