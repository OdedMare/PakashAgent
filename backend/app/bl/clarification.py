"""A clarification continues the request; it does not replace it.

Shared by the read path (`planner`) and the write path (`changes`): when a
turn asked the manager a question, their answer and the held request are read
as one sentence. Plain text rather than a parsed pending-intent record -- the
sentence is what both readers already read, and a structured duplicate of it
is a second thing to keep in sync.
"""

from typing import Any

_MAX_TEXT_CHARS = 4000


def _bounded(value: Any) -> str:
    return value.strip()[:_MAX_TEXT_CHARS] if isinstance(value, str) else ""


def resume(pending: str, reply: str) -> str:
    """The held request and the manager's answer to it, read as one.

    Joined rather than replaced: "ערב" is not a request — it is the missing
    half of one, and dropping the half that carried the verb is how a
    clarification turns into a new, emptier question.
    """
    pending, reply = _bounded(pending), _bounded(reply)
    if not pending:
        return reply
    if not reply:
        return pending
    # An answer that already restates the request is not appended to itself.
    if pending in reply:
        return reply
    return "%s (%s)" % (pending, reply)
