"""Bounding what the model returns, and shaping what it is shown."""

from typing import Any, List, Optional

from app.bl.planner.schema import MAX_CALLS_PER_TURN, MAX_OPTIONS
from app.bl.tools import TOOL_NAMES

MAX_TEXT_CHARS = 4000
_MAX_OPTION_LABEL_CHARS = 120
_MAX_PREFERENCES = 40


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def bounded(value: Any, limit: int = MAX_TEXT_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return text(value)


def pretty(hours: Any) -> str:
    try:
        return "%g" % round(float(hours), 1)
    except (TypeError, ValueError):
        return "0"


def resume(pending: str, reply: str) -> str:
    """The original request and the manager's clarification, read as one.

    Joined rather than replaced. "ערב" is not a request — it is the missing
    half of one, and dropping the half that carried the verb is how a
    clarification turns into a new, emptier question. Plain text rather than
    a parsed intent: the sentence is what both readers already read.
    """
    pending, reply = bounded(pending), bounded(reply)
    if not pending:
        return reply
    if not reply:
        return pending
    # An answer that already restates the request is not appended to itself.
    if pending in reply:
        return reply
    return "%s (%s)" % (pending, reply)


def is_question(value: str) -> bool:
    return text(value).endswith(("?", "؟"))


def tool_calls(offered: Any) -> List[dict]:
    """Tool calls the model asked for, bounded to ones that exist."""
    if not isinstance(offered, list):
        return []
    calls = []
    for item in offered[:MAX_CALLS_PER_TURN]:
        if not isinstance(item, dict) or text(item.get("tool")) not in TOOL_NAMES:
            continue
        arguments = item.get("arguments")
        calls.append({
            "tool": text(item.get("tool")),
            "arguments": arguments if isinstance(arguments, dict) else {},
        })
    return calls


def question(offered: Any) -> Optional[dict]:
    """One bounded question, or none for a completed answer."""
    if not isinstance(offered, dict) or not bounded(offered.get("question")):
        return None
    return {
        "question": bounded(offered.get("question")),
        "recommendation": bounded(offered.get("recommendation")),
        "why": bounded(offered.get("why")),
        "options": _options(offered.get("options")),
    }


def _options(offered: Any) -> List[dict]:
    """Concrete, deduplicated answers; one item is not a meaningful menu."""
    if not isinstance(offered, list):
        return []
    options, seen = [], set()
    for item in offered[:MAX_OPTIONS]:
        if not isinstance(item, dict):
            continue
        label = bounded(item.get("label"), _MAX_OPTION_LABEL_CHARS)
        answer = bounded(item.get("answer"))
        if not label or not answer or label in seen:
            continue
        seen.add(label)
        options.append({"label": label, "answer": answer})
    return options if len(options) > 1 else []


def plain_question(sentence: str) -> dict:
    return {"question": sentence, "recommendation": "", "why": "", "options": []}


def profile_for_model(profile: dict) -> dict:
    """The roster and the vocabulary, not the whole period.

    The tools are what fetch schedule rows; including them here would put
    back the wall of JSON that having tools was meant to remove.
    """
    profile = profile if isinstance(profile, dict) else {}
    return {
        "workplace": profile.get("workplace") or {},
        "employees": profile.get("employees") or [],
        "shifts": profile.get("shifts") or [],
        "rules": profile.get("rules") or [],
    }


def period_for_model(period: Optional[dict]) -> dict:
    if not isinstance(period, dict):
        return {}
    return {
        "id": text(period.get("id")),
        "starts_on": iso(period.get("starts_on")),
        "ends_on": iso(period.get("ends_on")),
        "status": text(period.get("status")),
    }


def preferences_for_model(preferences: Optional[List[dict]]) -> List[dict]:
    """Active preferences as context, handed over as reported speech.

    A preference is a standing wish, and a standing wish never authorises a
    write: the confirmation step is unchanged by anything in this list.
    """
    return [
        {
            "kind": text(row.get("kind")),
            "subject": text(row.get("subject")),
            "text": bounded(row.get("text")),
        }
        for row in preferences or [] if isinstance(row, dict)
    ][:_MAX_PREFERENCES]


def names(rows: Any) -> List[str]:
    return [text(row.get("name")) for row in rows or [] if isinstance(row, dict)]
