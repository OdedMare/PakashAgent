"""Persistence around the stateless intro interview.

`IntroInterview` decides what to ask; this decides what to remember. Keeping
them apart is what lets the interview stay a pure function of the
conversation — the piece that made it testable against a fake model without a
database.

The turn shape is the `plan-chat` one ported from AiSummryIO: the model is
handed the conversation plus the draft so far and returns the draft again,
merged. The difference from the reference is who holds that draft between
turns. There the client replays it; here the session does, so a boss who
refreshes — or opens the app on a second machine — resumes the profile they
had rather than the empty one their browser happened to keep.

Two methods here are not turns at all. `finish` ends the interview on what
has been gathered so far, and `extend` reopens a finished one to add to it.
Together they make the profile a thing the manager grows rather than a gate
they must clear in one sitting — the interview can be left the moment it is
useful, and returned to when it is not enough.

Every method takes the team the caller is authenticated into and passes it
down to the repository, which filters on it. The team is never taken from the
request body — it comes from the signed session cookie, so a boss cannot
reach another workspace's interview by naming it.
"""

from typing import List, Optional

from app.bl.interview import IntroInterview, empty_draft, scheduling_gaps
from app.common.errors import AgentError, ConflictError

# What a turn stores and serves. Named once because the payload written to
# the turn, the pending question, and the HTTP response are the same fields.
_TURN_FIELDS = (
    "reply", "question", "resolved", "open_points", "awaiting_confirmation",
    "ready", "draft",
)

# What the manager says by pressing the two buttons that are not an answer.
# Sent as their own message rather than as a flag, for the same reason a
# clicked option is: the model reads one conversation, and a turn that
# changes subject without a sentence explaining why is a turn the next one
# cannot make sense of.
FINISH_MESSAGE = "אני רוצה לסיים את הראיון כאן ולעבור לשיבוץ עם מה שיש."
EXTEND_MESSAGE = "אני רוצה להשלים עוד מידע על מקום העבודה."

# The agent's closing line when the interview is ended early and nothing
# blocks a schedule. Written here rather than asked of the model: it is the
# same sentence every time, it says what the button did, and spending a
# generation on it would only make finishing slower and less predictable.
# The account of the workplace itself is the profile, which the summary
# screen renders — this does not describe it.
CLOSING_REPLY = (
    "סיימנו כאן. זה מה שנאסף עד עכשיו, ואפשר לבנות איתו סידור. "
    "מה שלא הספקנו לכסות אפשר להשלים בכל שלב — הראיון ממשיך מהמקום הזה."
)


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
        answered question replaced by a near-duplicate. The pending turn is
        stored precisely so this path is free.
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

    def finish(self, session_id: str, team_id: str) -> dict:
        """End the interview now, on whatever has been gathered.

        The manager's way out of the topic list. Twenty-one topics is the
        thorough version of this conversation, not the only one, and a boss
        who wants a schedule this afternoon should not have to answer all of
        them first — what they have said is written as the profile and the
        management area opens against it.

        What is missing is never guessed at. `scheduling_gaps` names the few
        facts a schedule cannot be built without, and while any of them
        stands the session is *not* completed: the interview narrows to
        exactly those and asks. Everything else stays an open point and can
        be filled in later through `extend`, which is what makes stopping
        early a pause rather than a decision the manager is stuck with.
        """
        session = self._repository.get_session(session_id, team_id)
        if session["status"] == "complete":
            # Already finished — by a confirmed summary or by an earlier
            # press of this same button. Serving the result is the honest
            # answer to "finish"; a conflict would only be one for a second
            # click of a button that already did what it says.
            return _completed(session)
        draft = (session["pending"] or {}).get("draft") or empty_draft()
        self._repository.append_turn(session_id, "user", FINISH_MESSAGE)
        gaps = scheduling_gaps(draft)
        if gaps:
            return self._advance(session_id, team_id, focus=gaps)
        # The draft is the profile as the manager left it. It is written
        # unchanged rather than re-asked of the model: a closing generation
        # could only restate what is already in the draft, and a model that
        # decided to keep interviewing would override a decision that is the
        # manager's to make.
        self._repository.append_turn(
            session_id, "assistant", CLOSING_REPLY,
            dict(_pending(draft), reply=CLOSING_REPLY),
        )
        return _completed(
            self._repository.complete(session_id, team_id, draft)
        )

    def extend(self, team_id: str) -> dict:
        """Reopen the finished interview so more can be added to it.

        The other half of finishing early: the profile is the last thing the
        manager agreed to, never a final answer. A workplace taught in a
        hurry — or one that has changed since — is completed by *continuing
        the same conversation*, so the agent still knows everything already
        settled and the manager answers only what is new. Starting a second
        interview would ask for all of it again.

        The stored profile stays on the row while the session is open, so the
        management area keeps working off the last agreed version until a new
        one is confirmed. Nothing is taken away in order to add to it.
        """
        active = self._repository.active_session(team_id)
        if active is not None:
            # Already open. Resuming costs no model call, which is the right
            # answer to "let me add something" when the interview never
            # closed in the first place.
            return self.resume(active["id"], team_id)
        session = self._repository.latest_session(team_id)
        if session is None:
            return self.start(team_id)
        self._repository.reopen(
            session["id"], team_id, _pending(session["profile"])
        )
        self._repository.append_turn(session["id"], "user", EXTEND_MESSAGE)
        return self._advance(session["id"], team_id)

    def _advance(
        self,
        session_id: str,
        team_id: str,
        focus: Optional[List[str]] = None,
    ) -> dict:
        """One model turn: replay the history, merge, store, return.

        The draft handed to the model is the one the last turn produced, read
        back from the session rather than taken from the request, so a stale
        or edited client copy can never rewrite what was already agreed.

        `focus` is passed only by `finish`, and carries the gaps that stopped
        it: the interview then asks about those instead of resuming the topic
        list the manager has just said they are done with.
        """
        session = self._repository.get_session(session_id, team_id)
        history = [
            {"role": row["role"], "content": row["content"]}
            for row in session["turns"]
        ]
        draft = (session["pending"] or {}).get("draft")
        result = self._interview.next_turn(history, draft, focus=focus)
        pending = {key: result[key] for key in _TURN_FIELDS}
        # The reply is the turn's content; the question, the draft, and the
        # rest ride along as payload so the UI can re-render the buttons a
        # past turn offered instead of inferring them from prose.
        self._repository.append_turn(
            session_id, "assistant", result["reply"], pending
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


def _pending(draft) -> dict:
    """A stored turn holding nothing but a draft.

    Two paths need one: the closing turn of an early finish, which asks
    nothing, and a reopened session, whose draft is the profile it was
    completed with. Both go through the same shape the model's turns are
    stored in, so `_advance` reads the draft back from one place.
    """
    return {
        "reply": "", "question": None, "resolved": [], "open_points": [],
        "awaiting_confirmation": False, "ready": False,
        "draft": draft or empty_draft(),
    }


def _turn(session_id: str, pending: dict, turns) -> dict:
    return {
        "session_id": session_id,
        "status": "question",
        "turns": [_message(row) for row in turns],
        "profile": None,
        # Carried on every turn, not only on the one that refused to finish:
        # what blocks a schedule is a fact about the draft, and the manager
        # deciding whether to stop here is exactly who it is for.
        "gaps": scheduling_gaps(pending.get("draft")),
        **pending,
    }


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
        # Empty by construction on the finish path — a profile with gaps is
        # never completed — but computed rather than hardcoded, so a profile
        # written before this check existed still reports honestly.
        "gaps": scheduling_gaps(profile),
        "turns": [_message(row) for row in session["turns"]],
        "profile": profile,
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
