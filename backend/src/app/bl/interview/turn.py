"""One model answer, bounded and normalised into the turn the manager sees."""

from typing import List, Optional

from app.bl.interview.draft import merged_draft, missing_topics
from app.bl.interview.schema import MAX_OPTIONS
from app.bl.interview.text import as_dict, bounded, lines, unique

# A label is a button caption; the full sentence lives in `answer`.
_MAX_OPTION_CHARS = 120

# Phrasings that announce an update rather than report one. The prompt
# forbids these outright; this is the code-side net, since `reply` is prose
# and cannot be schema-constrained. Matched as substrings on the verb and kept
# deliberately short: a false positive puts a line in the panel the manager
# cannot act on.
_PROMISE_MARKERS = (
    "אעדכן", "נעדכן", "אשמור", "נשמור", "ארשום", "נרשום",
    "אני מעדכן", "אני שומר", "אני רושם",
    # Past-tense claims are the most misleading form: they say the write is
    # already done.
    "עדכנתי", "עדכנו", "שמרתי", "שמרנו", "רשמתי", "רשמנו",
)
_UNRECORDED_ANSWER = "התשובה האחרונה לא נשמרה במלואה בפרופיל — כדאי לחזור עליה."
_UNRECORDED_REPLY = "לא הצלחתי לשמור את התשובה במלואה; השארתי אותה כנקודה פתוחה."
# Claims we can verify without interpreting prose: the model records the
# operating days but says it also recorded the employee list, or vice versa.
_CLAIMED_FIELDS = (
    (("רשימת העובדים", "העובדים"), ("employees",)),
    (("ימי הפעילות", "ימי העבודה"), ("workplace", "operating_days")),
)


def shape_turn(answer: dict, previous) -> dict:
    """The model's turn, bounded and normalized, plus the merged draft.

    `open_points` and `resolved` are deduplicated, not concatenated: both are
    replayed to the model every turn and come back carried forward, so a blind
    `+` stacked the code-generated line beside the model's echo of it, once
    per turn. A profile still owing a required field withdraws the
    confirmation turn, and `ready` is gated here rather than trusted.
    """
    question = parse_question(answer.get("question"))
    # `draft` is accepted as a compatibility fallback for JSON-only local
    # servers that may still follow a cached copy of the old prompt.
    merged = merged_draft(answer.get("draft_update", answer.get("draft")), previous)
    missing = missing_topics(merged)
    unkept = promised_unkept(answer, merged, previous)
    open_points = unique(lines(answer.get("open_points")) + missing)
    if unkept:
        open_points = unique(open_points + [_UNRECORDED_ANSWER])
    # An open question means the interview is still running, whatever the
    # model claimed, so it cannot also be awaiting confirmation.
    awaiting = bool(answer.get("awaiting_confirmation")) and question is None \
        and not missing
    result = {
        "reply": _UNRECORDED_REPLY if unkept else bounded(answer.get("reply")),
        "question": question,
        "resolved": unique(lines(answer.get("resolved"))),
        "open_points": open_points,
        "awaiting_confirmation": awaiting,
        "ready": is_ready(answer, question, awaiting) and not missing,
        "draft": merged,
    }
    if answer.get("_usage") is not None:
        result["_usage"] = answer.get("_usage")
    return result


def promised_unkept(answer: dict, merged: dict, previous) -> bool:
    """Whether this turn claimed to record something and recorded nothing.

    Both halves are required: an empty update alone is ordinary -- a turn
    that only asks a clarifying question settles no fact. Compared against
    the *merged* draft, so re-sending a field's existing value counts as
    recording nothing too.
    """
    reply = bounded(answer.get("reply"))
    if not reply or not any(marker in reply for marker in _PROMISE_MARKERS):
        return False
    previous = as_dict(previous)
    if merged == previous:
        return True
    for phrases, path in _CLAIMED_FIELDS:
        if any(phrase in reply for phrase in phrases) and \
                _at(previous, path) == _at(merged, path):
            return True
    return False


def _at(draft: dict, path: tuple):
    value = draft
    for key in path:
        value = as_dict(value).get(key)
    return value


def is_ready(answer: dict, question, awaiting: bool) -> bool:
    """Whether the profile may be treated as confirmed.

    A turn that still asks something, or that is only now presenting its
    summary for approval, is never ready however the model labelled itself.
    `ready` is what closes the session and writes the profile.
    """
    return bool(answer.get("ready")) and question is None and not awaiting


def parse_question(value) -> Optional[dict]:
    """The single question for this turn, or None when none is asked."""
    value = as_dict(value)
    asked = bounded(value.get("question"))
    if not asked:
        return None
    return {
        "topic_id": bounded(value.get("topic_id")),
        "question": asked,
        "recommendation": bounded(value.get("recommendation")),
        "why": bounded(value.get("why")),
        "options": options(value),
    }


def options(question: dict) -> List[dict]:
    """Clickable answers, bounded and deduplicated.

    A clicked option is sent verbatim as the manager's own message, so an
    option missing its `answer` has nothing to send and is dropped rather
    than falling back to the label. A single usable option is still kept:
    some servers lose an item while degrading structured output.
    """
    offered = question.get("options")
    if not isinstance(offered, list):
        return []
    found, seen = [], set()
    for item in offered:
        item = as_dict(item)
        label = bounded(item.get("label"), _MAX_OPTION_CHARS)
        answer = bounded(item.get("answer"))
        if not label or not answer or label in seen:
            continue
        seen.add(label)
        found.append({"label": label, "answer": answer})
        if len(found) == MAX_OPTIONS:
            break
    return found
