"""Persistence around the stateless intro interview.

`IntroInterview` decides what to ask; this decides what to remember. Keeping
them apart is what lets the interview stay a pure function of the
conversation — the piece that made it testable against a fake model without a
database.

Every method takes the team the caller is authenticated into and passes it
down to the repository, which filters on it. The team is never taken from the
request body — it comes from the signed session cookie, so a boss cannot
reach another workspace's interview by naming it.
"""

from typing import Optional

from app.bl.interview import IntroInterview
from app.common.errors import AgentError, ConflictError


class InterviewService:
    def __init__(self, repository, llm):
        self._repository = repository
        self._interview = IntroInterview(llm)

    def start(self, team_id: str) -> dict:
        """Open a session and ask the first question.

        An interview already in progress for this team is resumed instead of
        being replaced. The interview belongs to the workspace, not to the
        browser that began it, so a boss opening the app on their phone
        continues rather than quietly starting a second one — and a model
        call is not spent re-asking a question already on screen elsewhere.
        """
        active = self._repository.active_session(team_id)
        if active is not None:
            return self.resume(active["id"], team_id)
        session = self._repository.create_session(team_id)
        return self._advance(session["id"], team_id)

    def resume(self, session_id: str, team_id: str) -> dict:
        """Return the session as it stands, without spending a model call.

        A refresh must not re-ask the model: the same conversation would
        produce a differently worded question, and the boss would see their
        answered question replaced by a near-duplicate. The pending question
        is stored precisely so this path is free.
        """
        session = self._repository.get_session(session_id, team_id)
        if session["status"] == "complete":
            return _completed(session)
        pending = session["pending"]
        if pending is None:
            return self._advance(session_id, team_id)
        return _turn(session_id, pending, session["turns"])

    def answer(self, session_id: str, team_id: str, content: str) -> dict:
        """Record the boss's answer and ask the next question."""
        session = self._repository.get_session(session_id, team_id)
        if session["status"] == "complete":
            raise ConflictError("הראיון כבר הושלם")
        text = (content or "").strip()
        if not text:
            raise AgentError("התשובה אינה יכולה להיות ריקה")
        self._repository.append_turn(session_id, "user", text)
        return self._advance(session_id, team_id)

    def _advance(self, session_id: str, team_id: str) -> dict:
        history = [
            {"role": row["role"], "content": row["content"]}
            for row in self._repository.history(session_id)
        ]
        result = self._interview.next_turn(history)
        if result["status"] == "complete":
            session = self._repository.complete(
                session_id, team_id, result["profile"]
            )
            return _completed(session)
        # The question text is the turn's content; the options and the
        # recommendation ride along as payload so the UI can re-render the
        # buttons a past turn offered instead of inferring them from prose.
        payload = {
            "question_id": result["question_id"],
            "question": result["question"],
            "recommendation": result["recommendation"],
            "options": result["options"],
            "allow_free_text": result["allow_free_text"],
        }
        self._repository.append_turn(
            session_id, "assistant", result["question"], payload
        )
        self._repository.save_pending(session_id, payload)
        return _turn(session_id, payload, self._repository.history(session_id))


def _turn(session_id: str, pending: dict, turns) -> dict:
    return {
        "session_id": session_id,
        "status": "question",
        "turns": [_message(row) for row in turns],
        "profile": None,
        **pending,
    }


def _completed(session: dict) -> dict:
    return {
        "session_id": session["id"],
        "status": "complete",
        "question_id": None,
        "question": None,
        "recommendation": None,
        "options": [],
        "allow_free_text": False,
        "turns": [_message(row) for row in session["turns"]],
        "profile": session["profile"],
    }


def _message(row: dict) -> dict:
    payload = row.get("payload") or {}
    return {
        "role": row["role"],
        "content": row["content"],
        "options": payload.get("options", []),
        "recommendation": payload.get("recommendation"),
    }


__all__ = ["InterviewService"]
