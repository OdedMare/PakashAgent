"""`InterviewService`: the session around the stateless intro interview."""

import logging
from threading import Thread

from app.bl.interview import IntroInterview, empty_draft
from app.bl.interview_service import responses
from app.bl.interview_service.history import TurnHistory
from app.bl.interview_service.seeding import completeness, seeded_state
from app.common.errors import AgentError, ConflictError

_log = logging.getLogger("pakash.interview")
_GENERIC_FAILURE = "יצירת השאלה נכשלה. אפשר לנסות שוב."


def _launch_thread(target, *args) -> None:
    # ponytail: process-local jobs do not survive a server restart; move this
    # to a durable queue only if interrupted interviews become common.
    Thread(target=target, args=args, daemon=True).start()


class InterviewService:
    def __init__(self, repository, llm, launch=None):
        self._repository = repository
        self._interview = IntroInterview(llm)
        self._launch = launch or _launch_thread

    def start(self, team_id: str, seed: dict = None) -> dict:
        """Open a session and ask the first question.

        An interview already in progress for this team is resumed instead of
        being replaced: it belongs to the workspace, not to the browser.
        """
        active = self._repository.active_session(team_id)
        if active is not None:
            return self.resume(active["id"], team_id)
        session = self._repository.create_session(team_id)
        return self._queue(session["id"], team_id, seeded_state(seed) if seed else None)

    def start_follow_up(self, team_id: str, question: str) -> dict:
        """Open a resumable interview seeded with the current profile.

        The copilot may notice the gap, but it never answers it. The existing
        profile is the draft, so a follow-up adds knowledge rather than
        rebuilding the workplace from an empty form.
        """
        active = self._repository.active_session(team_id)
        if active is not None:
            return self.resume(active["id"], team_id)
        session = self._repository.create_session(team_id)
        return self._queue(session["id"], team_id, {
            "draft": self._repository.team_profile(team_id) or empty_draft(),
            "resolved": [],
            "open_points": [question],
            "reply": "",
        })

    def resume(self, session_id: str, team_id: str) -> dict:
        """Return the session as it stands, without spending a model call.

        A refresh must not re-ask the model: the same conversation would
        produce a differently worded question.
        """
        session = self._repository.get_session(session_id, team_id)
        if session["status"] == "complete":
            return responses.completed(session)
        pending, turns = session["pending"], session["turns"]
        if pending is None:
            return self._queue(session_id, team_id, None)
        if pending.get("_processing"):
            return responses.processing(session_id, pending, turns)
        if pending.get("_error"):
            return responses.failed(session_id, pending, turns)
        if _stalled(pending):
            # Repair sessions created before the missing-question guard; they
            # otherwise resume forever on a reply with nothing to answer.
            return self._queue(session_id, team_id, pending)
        return responses.question_turn(session_id, pending, turns)

    def answer(
        self, session_id: str, team_id: str, content: str, mode: str = "answer",
    ) -> dict:
        """Record the boss's answer and ask the next question."""
        session = self._repository.get_session(session_id, team_id)
        if session["status"] == "complete":
            raise ConflictError("הראיון כבר הושלם")
        pending = session.get("pending") or {}
        if pending.get("_processing"):
            raise ConflictError("הסוכן עדיין מעבד את התשובה הקודמת")
        if pending.get("_error"):
            raise ConflictError("יש לנסות שוב את התשובה הקודמת")
        text = (content or "").strip()
        if not text:
            raise AgentError("התשובה אינה יכולה להיות ריקה")
        payload = {"mode": "correction"} if mode == "correction" else None
        self._repository.append_turn(session_id, "user", text, payload)
        return self._queue(session_id, team_id, pending)

    def retry(self, session_id: str, team_id: str) -> dict:
        """Retry a failed generation without recording the answer twice."""
        session = self._repository.get_session(session_id, team_id)
        pending = session.get("pending") or {}
        if session["status"] == "complete":
            return responses.completed(session)
        if pending.get("_processing"):
            return responses.processing(session_id, pending, session["turns"])
        if not pending.get("_error"):
            raise ConflictError("אין פעולת ראיון שנכשלה")
        return self._queue(session_id, team_id, pending)

    def end(self, session_id: str, team_id: str) -> dict:
        """Close the interview now, with whatever has been collected (D22).

        The manager's own act, not the agent's conclusion, and **no model
        call** -- an escape hatch that can fail on a slow model is not one.
        What is still owed is recorded on the profile as `completeness`, which
        `bl/tools` reads back when the manager asks what the agent is missing.
        Ending twice ends the same interview.
        """
        session = self._repository.get_session(session_id, team_id)
        if session["status"] == "complete":
            return responses.completed(session)
        pending = session["pending"] or {}
        draft = pending.get("draft") or empty_draft()
        profile = dict(draft, completeness=completeness(pending, draft))
        return responses.completed(self._repository.complete(session_id, team_id, profile))

    def _advance(self, session_id: str, team_id: str) -> dict:
        """One model turn: replay the history, merge, store, return.

        The draft handed to the model is read back from the session rather
        than taken from the request, so a stale client copy can never rewrite
        what was already agreed.
        """
        session = self._repository.get_session(session_id, team_id)
        history = TurnHistory(session["turns"])
        state = history.state_for_model(session["pending"])
        result = self._interview.next_turn(history.replayed(), state.get("draft"), state)
        # Ending is allowed while the model works; its result must not
        # resurrect or overwrite that profile.
        if self._repository.get_session(session_id, team_id)["status"] == "complete":
            return {}
        pending = {key: result[key] for key in responses.TURN_FIELDS}
        if result.get("_usage"):
            pending["_usage"] = result["_usage"]
        # The question, the draft and the rest ride along as payload so the UI
        # can re-render past buttons; an empty reply is stored under its
        # question so the thread and the replayed history have content.
        content = result["reply"] or responses.fallback_content(result)
        self._repository.append_turn(session_id, "assistant", content, pending)
        if result["ready"]:
            # `bl/interview` gates `ready`, so a mislabelled turn cannot get here.
            session = self._repository.complete(session_id, team_id, result["draft"])
            return responses.completed(session)
        self._repository.save_pending(session_id, pending)
        return responses.question_turn(
            session_id, pending, self._repository.history(session_id)
        )

    def _queue(self, session_id: str, team_id: str, state) -> dict:
        self._repository.save_pending(session_id, responses.processing_pending(state))
        self._launch(self._advance_safely, session_id, team_id)
        # An injected inline launcher keeps unit tests deterministic; the
        # production thread normally leaves this in `processing` here.
        return self.resume(session_id, team_id)

    def _advance_safely(self, session_id: str, team_id: str) -> None:
        try:
            self._advance(session_id, team_id)
        except Exception as exc:
            _log.exception("interview generation failed session=%s", session_id)
            self._record_failure(session_id, team_id, exc)

    def _record_failure(self, session_id: str, team_id: str, exc: Exception) -> None:
        try:
            session = self._repository.get_session(session_id, team_id)
            if session["status"] == "complete":
                return
            pending = dict(session.get("pending") or {})
            pending["_processing"] = False
            pending["_error"] = str(exc) if isinstance(exc, AgentError) else _GENERIC_FAILURE
            self._repository.save_pending(session_id, pending)
        except Exception:
            _log.exception("could not persist interview failure session=%s", session_id)


def _stalled(pending: dict) -> bool:
    return (
        pending.get("question") is None
        and not pending.get("awaiting_confirmation")
        and not pending.get("ready")
    )
