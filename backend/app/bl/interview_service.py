"""Persistence around the stateless intro interview.

`IntroInterview` decides what to ask; this decides what to remember. Keeping
them apart is what lets the interview stay a pure function of the
conversation — the piece that made it testable against a fake model without a
database.

The turn shape is the `plan-chat` one ported from AiSummryIO: the model is
handed the latest exchange plus the structured state and returns a sparse
draft update. The session merges and owns that state, so a boss who refreshes
— or opens the app on a second machine — resumes the profile they had rather
than the empty one their browser happened to keep.

Every method takes the team the caller is authenticated into and passes it
down to the repository, which filters on it. The team is never taken from the
request body — it comes from the signed session cookie, so a boss cannot
reach another workspace's interview by naming it.
"""

import logging
from threading import Thread

from app.bl.interview import IntroInterview, empty_draft, missing_topics
from app.common.errors import AgentError, ConflictError

# What a turn stores and serves. Named once because the payload written to
# the turn, the pending question, and the HTTP response are the same fields.
_TURN_FIELDS = (
    "reply", "question", "resolved", "open_points", "awaiting_confirmation",
    "ready", "draft",
)

_log = logging.getLogger("pakash.interview")


def _launch_thread(target, *args) -> None:
    # ponytail: process-local jobs do not survive a server restart; move this
    # to a durable queue only if interrupted interviews become common.
    Thread(target=target, args=args, daemon=True).start()


class InterviewService:
    def __init__(self, repository, llm, launch=None):
        self._repository = repository
        self._interview = IntroInterview(llm)
        self._launch = launch or _launch_thread

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
        return self._queue(session["id"], team_id, None)

    def start_follow_up(self, team_id: str, question: str) -> dict:
        """Open a resumable interview seeded with the current profile.

        The copilot may notice the gap, but it never answers it. The existing
        profile is the draft so a follow-up adds knowledge instead of asking
        the manager to rebuild the workplace from an empty form.
        """
        active = self._repository.active_session(team_id)
        if active is not None:
            return self.resume(active["id"], team_id)
        session = self._repository.create_session(team_id)
        state = {
            "draft": self._repository.team_profile(team_id) or empty_draft(),
            "resolved": [],
            "open_points": [question],
            "reply": "",
        }
        return self._queue(session["id"], team_id, state)

    def resume(self, session_id: str, team_id: str) -> dict:
        """Return the session as it stands, without spending a model call.

        A refresh must not re-ask the model: the same conversation would
        produce a differently worded question, and the boss would see their
        answered question replaced by a near-duplicate. The pending turn is
        stored precisely so this path is free.
        """
        session = self._repository.get_session(session_id, team_id)
        if session["status"] == "complete":
            return _completed(session)
        pending = session["pending"]
        if pending is None:
            return self._queue(session_id, team_id, None)
        if pending.get("_processing"):
            return _processing(session_id, pending, session["turns"])
        if pending.get("_error"):
            return _failed(session_id, pending, session["turns"])
        return _turn(session_id, pending, session["turns"])

    def answer(self, session_id: str, team_id: str, content: str) -> dict:
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
        self._repository.append_turn(session_id, "user", text)
        return self._queue(session_id, team_id, pending)

    def retry(self, session_id: str, team_id: str) -> dict:
        """Retry a failed generation without recording the answer twice."""
        session = self._repository.get_session(session_id, team_id)
        pending = session.get("pending") or {}
        if session["status"] == "complete":
            return _completed(session)
        if pending.get("_processing"):
            return _processing(session_id, pending, session["turns"])
        if not pending.get("_error"):
            raise ConflictError("אין פעולת ראיון שנכשלה")
        return self._queue(session_id, team_id, pending)

    def end(self, session_id: str, team_id: str) -> dict:
        """Close the interview now, with whatever has been collected.

        The manager's own act, not the agent's conclusion. `_is_ready` still
        governs what the *model* may declare finished; this is the other
        door, and the two are deliberately separate — an agent that could
        reach this would be deciding it had asked enough, which is the
        judgement the confirmation turn exists to keep with the manager.

        **No model call.** Ending is the escape hatch from an interview that
        is too long, and an escape hatch that can fail on a slow or
        rate-limited model is not one. The draft already on the session is
        what gets written, so ending costs nothing and cannot half-happen.

        What is still owed is recorded on the profile rather than discarded.
        The scheduler runs on a partial profile and produces a partial
        answer; the gaps are what explains why, so they travel with the
        profile they belong to and `bl/tools.py` reads them back when the
        manager asks the agent what it is missing.
        """
        session = self._repository.get_session(session_id, team_id)
        if session["status"] == "complete":
            # Already closed, by this door or by confirmation. Serving the
            # finished session is what a double-clicked button deserves —
            # `complete` would raise, and there is nothing here to conflict
            # over, since ending twice ends the same interview.
            return _completed(session)
        pending = session["pending"] or {}
        draft = pending.get("draft") or empty_draft()
        profile = dict(draft, completeness=_completeness(pending, draft))
        session = self._repository.complete(session_id, team_id, profile)
        return _completed(session)

    def _advance(self, session_id: str, team_id: str) -> dict:
        """One model turn: replay the history, merge, store, return.

        The draft handed to the model is the one the last turn produced, read
        back from the session rather than taken from the request, so a stale
        or edited client copy can never rewrite what was already agreed.
        """
        session = self._repository.get_session(session_id, team_id)
        history = [_replayed(row) for row in session["turns"]]
        state = session["pending"] or {}
        draft = state.get("draft")
        result = self._interview.next_turn(history, draft, state)
        # Ending the interview is deliberately allowed while the model is
        # working. Its result must not resurrect or overwrite that profile.
        current = self._repository.get_session(session_id, team_id)
        if current["status"] == "complete":
            return {}
        pending = {key: result[key] for key in _TURN_FIELDS}
        if result.get("_usage"):
            pending["_usage"] = result["_usage"]
        # The reply is the turn's content; the question, the draft, and the
        # rest ride along as payload so the UI can re-render the buttons a
        # past turn offered instead of inferring them from prose.
        #
        # A turn whose prose is empty still has to be stored — the question
        # and its options live in the payload, and dropping the row would
        # lose the buttons the boss is looking at. The question text stands
        # in as the content so the thread has something to show and the
        # replayed history has something for the model to read.
        content = result["reply"] or _fallback_content(result)
        self._repository.append_turn(
            session_id, "assistant", content, pending
        )
        if result["ready"]:
            # `ready` means the boss confirmed the summary on the previous
            # turn. `bl/interview.py` gates it, so a model that mislabels an
            # open question or an incomplete profile cannot reach here.
            session = self._repository.complete(
                session_id, team_id, result["draft"]
            )
            return _completed(session)
        self._repository.save_pending(session_id, pending)
        return _turn(session_id, pending, self._repository.history(session_id))

    def _queue(self, session_id: str, team_id: str, state) -> dict:
        pending = _processing_pending(state)
        self._repository.save_pending(session_id, pending)
        self._launch(self._advance_safely, session_id, team_id)
        # An injected inline launcher keeps unit tests deterministic; the
        # production thread normally leaves this in `processing` here.
        return self.resume(session_id, team_id)

    def _advance_safely(self, session_id: str, team_id: str) -> None:
        try:
            self._advance(session_id, team_id)
        except Exception as exc:
            _log.exception("interview generation failed session=%s", session_id)
            try:
                session = self._repository.get_session(session_id, team_id)
                if session["status"] == "complete":
                    return
                pending = dict(session.get("pending") or {})
                pending["_processing"] = False
                pending["_error"] = (
                    str(exc) if isinstance(exc, AgentError)
                    else "יצירת השאלה נכשלה. אפשר לנסות שוב."
                )
                self._repository.save_pending(session_id, pending)
            except Exception:
                _log.exception(
                    "could not persist interview failure session=%s",
                    session_id,
                )


def _completeness(pending: dict, draft: dict) -> dict:
    """What an ended interview still owes, recorded on its own profile.

    Two lists, kept apart because they answer different questions. The
    required topics come from `bl/interview.py` and are what the *scheduler*
    cannot run without — no shift vocabulary means no grid, and D9 forbids
    inventing one. The open points are the agent's own running list of what
    it has not settled: real gaps, but ones a manager can schedule around.

    `complete: False` is what marks a profile as ended early. A profile
    confirmed the ordinary way carries no such key at all, so its absence
    reads as "finished" without anything having to be backfilled.
    """
    return {
        "complete": False,
        "missing_topics": missing_topics(draft),
        "open_points": list(pending.get("open_points") or []),
        "resolved": list(pending.get("resolved") or []),
    }


def _fallback_content(result: dict) -> str:
    """What an assistant turn says when the model returned no prose.

    `reply` is only ever empty because the model left it so; the turn is
    still real, so it is stored under the question it asks rather than as a
    blank row that renders as a gap in the thread.
    """
    question = result.get("question") or {}
    return question.get("question") or ""


def _replayed(row: dict) -> dict:
    """One stored row as the model reads it back.

    Rows written before an empty `reply` was stored under its question are
    blank in `content` while still carrying that question in their payload,
    so the turn is recovered from there rather than replayed empty. The
    interview is a function of its history: a turn that vanishes takes its
    question with it, and the model re-asks something already answered.
    """
    content = row["content"]
    if not (content or "").strip():
        payload = row.get("payload") or {}
        question = payload.get("question") or {}
        content = question.get("question") or ""
    return {"role": row["role"], "content": content}


def _turn(session_id: str, pending: dict, turns) -> dict:
    return {
        "session_id": session_id,
        "status": "question",
        "turns": [_message(row) for row in turns],
        "profile": None,
        **pending,
    }


def _processing_pending(previous) -> dict:
    previous = previous or {}
    return {
        "reply": previous.get("reply", ""),
        "question": None,
        "resolved": list(previous.get("resolved") or []),
        "open_points": list(previous.get("open_points") or []),
        "awaiting_confirmation": False,
        "ready": False,
        "draft": previous.get("draft"),
        "_processing": True,
        "_error": None,
    }


def _processing(session_id: str, pending: dict, turns) -> dict:
    return {
        "session_id": session_id,
        "status": "processing",
        "reply": pending.get("reply", ""),
        "question": None,
        "resolved": pending.get("resolved", []),
        "open_points": pending.get("open_points", []),
        "awaiting_confirmation": False,
        "ready": False,
        "draft": pending.get("draft") or empty_draft(),
        "turns": [_message(row) for row in turns],
        "profile": None,
        "error": None,
    }


def _failed(session_id: str, pending: dict, turns) -> dict:
    result = _processing(session_id, pending, turns)
    result["status"] = "error"
    result["error"] = pending.get("_error")
    return result


def _completed(session: dict) -> dict:
    profile = session["profile"]
    return {
        "session_id": session["id"],
        "status": "complete",
        "reply": "",
        "question": None,
        "resolved": [],
        "open_points": [],
        "awaiting_confirmation": False,
        "ready": True,
        # The finished profile is served as the draft too, so the summary
        # panel reads one field whether the interview is running or done.
        "draft": profile or empty_draft(),
        "turns": [_message(row) for row in session["turns"]],
        "profile": profile,
        "error": None,
    }


def _message(row: dict) -> dict:
    """One thread row as the UI replays it.

    `options` and `recommendation` are lifted out of the stored question so a
    past assistant turn can re-render its buttons without the client reaching
    into an object that is null on every user row.
    """
    payload = row.get("payload") or {}
    question = payload.get("question") or {}
    return {
        "role": row["role"],
        "content": row["content"],
        "question": payload.get("question"),
        "options": question.get("options", []),
        "recommendation": question.get("recommendation"),
    }


__all__ = ["InterviewService"]
