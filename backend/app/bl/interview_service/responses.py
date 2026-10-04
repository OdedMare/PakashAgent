"""The shapes an interview session is served in: question, processing,
error, or complete. Every route answers with one of these."""

from app.bl.interview import empty_draft

# What a turn stores and serves. Named once because the payload written to
# the turn, the pending question, and the HTTP response are the same fields.
TURN_FIELDS = (
    "reply", "question", "resolved", "open_points", "awaiting_confirmation",
    "ready", "draft",
)


def message(row: dict) -> dict:
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
        "mode": payload.get("mode", ""),
    }


def question_turn(session_id: str, pending: dict, turns) -> dict:
    return {
        "session_id": session_id,
        "status": "question",
        "turns": [message(row) for row in turns],
        "profile": None,
        **pending,
    }


def processing_pending(previous) -> dict:
    """The pending state stored while the model is working on a turn."""
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


def processing(session_id: str, pending: dict, turns) -> dict:
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
        "turns": [message(row) for row in turns],
        "profile": None,
        "error": None,
    }


def failed(session_id: str, pending: dict, turns) -> dict:
    result = processing(session_id, pending, turns)
    result["status"] = "error"
    result["error"] = pending.get("_error")
    return result


def completed(session: dict) -> dict:
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
        "turns": [message(row) for row in session["turns"]],
        "profile": profile,
        "error": None,
    }


def fallback_content(result: dict) -> str:
    """What an assistant turn says when the model returned no prose.

    The turn is still real, so it is stored under the question it asks rather
    than as a blank row that renders as a gap in the thread.
    """
    return (result.get("question") or {}).get("question") or ""
