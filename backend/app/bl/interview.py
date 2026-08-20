"""One conversational turn of the intro interview.

Ported from the `plan-chat` planners in AiSummryIO
(`bl/workflow_engine_pkg/conversational_planning.py`): the model interviews
the manager one question per turn, each question carrying a recommended
answer and clickable options, and every turn returns the draft profile so far
so the summary fills in as the interview proceeds rather than landing all at
once at the end.

The interview never acts on its own conclusion. A turn that still asks
something — or that is only now presenting its summary for approval — is not
ready, and `_is_ready` enforces that here rather than trusting the prompt to.

This module stays a pure function of the conversation. `interview_service`
owns the session and replays the history on every turn, which is what lets
this be tested against a fake model with no database.
"""

import json
from typing import Any, Dict, List, Optional

from app.bl.prompts import load
from app.common.errors import AgentError

# The interview is bounded at roughly the topic count, so history is not
# windowed for a context budget — this is a guard against a pathological
# session, not a summarization strategy.
_MAX_MESSAGES = 200
_MAX_MESSAGE_CHARS = 4000
_MAX_TEXT_CHARS = 20000
# Clickable answers per question. Past four the manager is reading a list
# instead of choosing, which is the deliberation the options exist to save.
_MAX_OPTIONS = 4
# A label is a button caption; the full sentence lives in `answer`.
_MAX_OPTION_CHARS = 120


INTERVIEW_TOPICS = (
    {
        "id": "workplace_mission",
        "question": "מה שם מקום העבודה ועל מה המשמרת אחראית?",
    },
    {
        "id": "success_criteria",
        "question": "איך יודעים שהמשמרת הצליחה?",
    },
    {
        "id": "operation_calendar",
        "question": "באילו ימים ושעות מקום העבודה פעיל?",
    },
    {
        "id": "planning_cycle",
        "question": "לאיזו תקופה בונים סידור ומתי נסגרת הגשת האילוצים?",
    },
    {
        "id": "shift_vocabulary",
        "question": "אילו סוגי משמרות קיימים ומה השעות של כל אחת?",
    },
    {
        "id": "staffing",
        "question": "כמה עובדים ותפקידים נדרשים בכל משמרת, והאם התקינה משתנה בין ימי השבוע?",
    },
    {
        "id": "employees",
        "question": "מי העובדים שמחזיקים את המשמרות, מה תפקידם ומה היקף העבודה הרגיל שלהם?",
    },
    {
        "id": "managers",
        "question": "האם מנהלי משמרת משובצים בעצמם, ולאילו סוגי משמרות?",
    },
    {
        "id": "qualifications",
        "question": "מי מוסמך לכל סוג משמרת ואיך מזהים את ההכשרה או המגבלה?",
    },
    {
        "id": "shadow_training",
        "question": "האם יש מתלמדים במשמרות צל ומה מדיניות החפיפה שלהם?",
    },
    {
        "id": "availability",
        "question": "איך אילוצים וזמינות נראים בלוח, והאם אילוץ יומי פוסל את כל המשמרות באותו יום?",
    },
    {
        "id": "casual_workers",
        "question": "האם יש עובדים מזדמנים, ואיך ומתי מתקבלת הזמינות שלהם?",
    },
    {
        "id": "on_call",
        "question": "האם קיימת כוננות, וכיצד היא נספרת בשעות ובהוגנות לעומת משמרת רגילה?",
    },
    {
        "id": "rest_and_weekend",
        "question": "מה כללי המנוחה, הלילות וסופי השבוע, כולל המשמרת האחרונה לפני יציאה לסוף שבוע?",
    },
    {
        "id": "fairness",
        "question": "איך מחלקים משמרות רצויות, לילות, סופי שבוע ושעות נוספות בצורה הוגנת?",
    },
    {
        "id": "rules",
        "question": "אילו כללים הם חובה ואילו העדפות רכות, בניסוח שלך?",
    },
    {
        "id": "availability_source",
        "question": "מאיפה מגיעים אילוצים, חופשות ושינויים, ומי אחראי לעדכן אותם?",
    },
    {
        "id": "recurring_constraints",
        "question": "האם קיימים אילוצים קבועים שחוזרים בכל תקופת סידור?",
    },
    {
        "id": "scheduling_authority",
        "question": "מי רשאי לשבץ ולאשר את הסידור, והאם הוא עובד במשמרות?",
    },
    {
        "id": "existing_schedule",
        "question": "האם יש סידורים קודמים או קובץ לדוגמה שמהם כדאי ללמוד?",
    },
    {
        "id": "conflict_policy",
        "question": "כשאי אפשר לעמוד בכל הדרישות, מה סדר העדיפויות ועל מה חייבים להתריע?",
    },
)


_PROFILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "workplace", "employees", "shifts", "dependencies", "rules",
        "availability_process", "constraint_deadline", "casual_worker_policy",
        "training_policy", "rest_policy", "weekend_policy", "fairness_policy",
        "conflict_policy", "existing_schedule_source", "summary",
    ],
    "properties": {
        "workplace": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "name", "mission", "success_criteria", "timezone",
                "operating_days", "planning_horizon", "scheduler_name",
                "scheduler_works_shifts",
            ],
            "properties": {
                "name": {"type": "string"},
                "mission": {"type": "string"},
                "success_criteria": {
                    "type": "array", "items": {"type": "string"},
                },
                "timezone": {"type": "string"},
                "operating_days": {
                    "type": "array", "items": {"type": "string"},
                },
                "planning_horizon": {"type": "string"},
                "scheduler_name": {"type": "string"},
                "scheduler_works_shifts": {"type": "boolean"},
            },
        },
        "employees": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name", "role", "workload", "eligible_shifts",
                    "is_shift_manager", "is_trainee",
                    "counts_toward_staffing", "can_train", "trainers",
                    "is_casual", "availability", "recurring_constraints",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "workload": {"type": "string"},
                    "eligible_shifts": {
                        "type": "array", "items": {"type": "string"},
                    },
                    "is_shift_manager": {"type": "boolean"},
                    "is_trainee": {"type": "boolean"},
                    "counts_toward_staffing": {"type": "boolean"},
                    "can_train": {"type": "boolean"},
                    "trainers": {
                        "type": "array", "items": {"type": "string"},
                    },
                    "is_casual": {"type": "boolean"},
                    "availability": {"type": "string"},
                    "recurring_constraints": {
                        "type": "array", "items": {"type": "string"},
                    },
                },
            },
        },
        "shifts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name", "purpose", "start_time", "end_time", "days",
                    "staffing", "is_on_call", "hour_weight",
                    "fairness_weight",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "purpose": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "days": {
                        "type": "array", "items": {"type": "string"},
                    },
                    "staffing": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["days", "headcount", "required_roles"],
                            "properties": {
                                "days": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "headcount": {"type": "integer", "minimum": 0},
                                "required_roles": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "is_on_call": {"type": "boolean"},
                    "hour_weight": {"type": "number", "minimum": 0},
                    "fairness_weight": {"type": "number", "minimum": 0},
                },
            },
        },
        "dependencies": {
            "type": "array", "items": {"type": "string"},
        },
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "priority"],
                "properties": {
                    "text": {"type": "string"},
                    "priority": {"type": "string", "enum": ["hard", "soft"]},
                },
            },
        },
        "availability_process": {"type": "string"},
        "constraint_deadline": {"type": "string"},
        "casual_worker_policy": {"type": "string"},
        "training_policy": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "shadow_shift_fraction", "shadow_shifts_per_week",
                "alternate_halves", "counts_toward_staffing",
            ],
            "properties": {
                "shadow_shift_fraction": {
                    "type": "number", "minimum": 0, "maximum": 1,
                },
                "shadow_shifts_per_week": {"type": "integer", "minimum": 0},
                "alternate_halves": {"type": "boolean"},
                "counts_toward_staffing": {"type": "boolean"},
            },
        },
        "rest_policy": {"type": "string"},
        "weekend_policy": {"type": "string"},
        "fairness_policy": {"type": "string"},
        "conflict_policy": {"type": "string"},
        "existing_schedule_source": {"type": "string"},
        "summary": {"type": "string"},
    },
}


# Every profile field the interview may fill. The draft is merged field by
# field across turns, so this is the list that decides what "carried forward"
# means — a field absent here would be silently dropped every turn.
_TEXT_FIELDS = (
    "availability_process", "constraint_deadline", "casual_worker_policy",
    "rest_policy", "weekend_policy", "fairness_policy", "conflict_policy",
    "existing_schedule_source", "summary",
)
_LIST_FIELDS = ("employees", "shifts", "dependencies", "rules")
_OBJECT_FIELDS = ("workplace", "training_policy")


_OPTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["label", "answer"],
    "properties": {
        # The button caption.
        "label": {"type": "string"},
        # The full sentence sent as the manager's own message when clicked.
        # An option without one has nothing to send, so both are required.
        "answer": {"type": "string"},
    },
}

_QUESTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["question", "recommendation", "why", "options"],
    "properties": {
        "question": {"type": "string"},
        "recommendation": {"type": "string"},
        "why": {"type": "string"},
        "options": {
            "type": "array", "items": _OPTION_SCHEMA, "maxItems": _MAX_OPTIONS,
        },
    },
}

INTERVIEW_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "reply", "question", "resolved", "open_points",
        "awaiting_confirmation", "ready", "draft",
    ],
    "properties": {
        "reply": {"type": "string"},
        # Null on the turn that presents the summary and on the turn that
        # finishes; a question object on every other turn.
        "question": {"oneOf": [_QUESTION_SCHEMA, {"type": "null"}]},
        "resolved": {"type": "array", "items": {"type": "string"}},
        "open_points": {"type": "array", "items": {"type": "string"}},
        "awaiting_confirmation": {"type": "boolean"},
        "ready": {"type": "boolean"},
        "draft": _PROFILE_SCHEMA,
    },
}


class IntroInterview:
    """Ask the next question and return the profile drafted so far.

    The caller owns persistence and passes the conversation back on every
    turn, so this stays a pure function of the history plus the draft it is
    handed.
    """

    def __init__(self, llm):
        self._llm = llm

    def next_turn(
        self, history: List[Dict[str, str]], draft: Optional[dict] = None,
    ) -> dict:
        """One turn: gather context, ask the model once, shape the answer."""
        payload = {
            "topics": INTERVIEW_TOPICS,
            "conversation": _validated_history(history),
            "draft_so_far": _as_dict(draft),
        }
        answer = self._ask(payload)
        return _result(answer, draft)

    def _ask(self, payload: dict) -> dict:
        # Loaded per turn rather than at import, so editing the markdown
        # takes effect without a restart. The loader caches the read.
        answer = self._llm.complete_json(
            load("interview"),
            json.dumps(payload, ensure_ascii=False),
            schema=INTERVIEW_RESPONSE_SCHEMA,
            flow="interview",
        )
        if not isinstance(answer, dict):
            raise AgentError("המודל החזיר תוצאת ראיון לא תקינה")
        return answer


def _result(answer: dict, previous) -> dict:
    """The model's turn, bounded and normalized, plus the merged draft."""
    usage = answer.get("_usage")
    question = _question(answer.get("question"))
    merged = _merged_draft(answer.get("draft"), previous)
    open_points = _lines(answer.get("open_points"))
    # An open question means the interview is still running, whatever the
    # model claimed, so it cannot also be awaiting confirmation.
    awaiting = bool(answer.get("awaiting_confirmation")) and question is None
    missing = _missing_topics(merged)
    open_points = open_points + missing
    if missing:
        # A profile still owing a required field is not a summary the manager
        # can meaningfully approve, so the confirmation turn is withdrawn
        # rather than shown over an incomplete draft.
        awaiting = False
    result = {
        "reply": _bounded(answer.get("reply")),
        "question": question,
        "resolved": _lines(answer.get("resolved")),
        "open_points": open_points,
        "awaiting_confirmation": awaiting,
        "ready": _is_ready(answer, question, awaiting) and not missing,
        "draft": merged,
    }
    if usage is not None:
        result["_usage"] = usage
    return result


def _is_ready(answer: dict, question, awaiting: bool) -> bool:
    """Whether the profile may be treated as confirmed.

    The interview does not finish before the manager confirms, so a turn that
    still asks something, or that is only now presenting its summary for
    approval, is never ready however the model labelled itself. Enforced here
    rather than trusted to the prompt: `ready` is what closes the session and
    writes the profile.
    """
    return bool(answer.get("ready")) and question is None and not awaiting


def _question(value) -> Optional[dict]:
    """The single question for this turn, or None when none is asked."""
    value = _as_dict(value)
    asked = _bounded(value.get("question"))
    if not asked:
        return None
    return {
        "question": asked,
        "recommendation": _bounded(value.get("recommendation")),
        "why": _bounded(value.get("why")),
        "options": _options(value),
    }


def _options(question: dict) -> List[dict]:
    """Clickable answers, bounded and deduplicated.

    A clicked option is sent verbatim as the manager's own message, so an
    option missing its `answer` has nothing to send and is dropped rather
    than falling back to the label — the label is a button caption, and
    sending it would put a fragment in the thread where a sentence belongs.

    One option is not a choice: the manager would be reading a menu with a
    single item next to the recommendation that already says the same thing.
    Below two, the recommendation carries the turn on its own.
    """
    offered = question.get("options")
    if not isinstance(offered, list):
        return []
    options, seen = [], set()
    for item in offered:
        item = _as_dict(item)
        label = _bounded(item.get("label"), _MAX_OPTION_CHARS)
        answer = _bounded(item.get("answer"))
        if not label or not answer or label in seen:
            continue
        seen.add(label)
        options.append({"label": label, "answer": answer})
        if len(options) == _MAX_OPTIONS:
            break
    return options if len(options) > 1 else []


def _merged_draft(offered, previous) -> dict:
    """This turn's draft over the last, so nothing agreed is dropped.

    The model rebuilds the draft from scratch every turn, and a turn that
    answers a narrow question by re-emitting only the field it touched would
    otherwise blank the twenty fields it did not — precisely at the
    confirmation turn, where the manager is asked to approve a summary that
    just lost most of its content.

    A field is carried forward only when this turn left it empty, so the
    model can still correct any value by actually restating it.
    """
    offered, previous = _as_dict(offered), _as_dict(previous)
    merged: Dict[str, Any] = {}
    for field in _TEXT_FIELDS:
        merged[field] = (
            _bounded(offered.get(field), _MAX_TEXT_CHARS)
            or _bounded(previous.get(field), _MAX_TEXT_CHARS)
        )
    for field in _LIST_FIELDS:
        value = offered.get(field)
        if not isinstance(value, list) or not value:
            value = previous.get(field)
        merged[field] = value if isinstance(value, list) else []
    for field in _OBJECT_FIELDS:
        value = _as_dict(offered.get(field))
        carried = _as_dict(previous.get(field))
        # Merged per key rather than whole: `workplace` holds eight fields
        # settled across different turns, and taking it as one blob would
        # make the last turn to mention it the only one that counts.
        merged[field] = dict(carried, **{
            key: item for key, item in value.items()
            if item != "" and item != [] and item is not None
        })
    return merged


# What `ready` requires beyond the model's own say-so. These are the fields
# the scheduler cannot run without: a profile missing one is not a finished
# interview whatever the model claimed, and the gap resurfaces as an open
# point rather than the manager discovering it after the session closed.
_REQUIRED_TOPICS = (
    ("workplace", "name", "חסר שם למקום העבודה."),
    ("workplace", "mission", "חסר תיאור האחריות של המשמרת."),
    ("workplace", "planning_horizon", "חסרה תקופת התכנון של הסידור."),
)


def _missing_topics(draft: dict) -> List[str]:
    """One line per required field the draft still owes."""
    missing = []
    for section, field, message in _REQUIRED_TOPICS:
        if not _bounded(_as_dict(draft.get(section)).get(field)):
            missing.append(message)
    if not draft.get("shifts"):
        missing.append("לא הוגדר אף סוג משמרת.")
    if not draft.get("employees"):
        missing.append("לא נרשם אף עובד.")
    return missing


def _validated_history(history) -> List[Dict[str, str]]:
    """The conversation, bounded, with only the two roles the prompt names.

    An empty message is dropped rather than rejected. The manager's own
    blank submission is already refused a layer up, where it can be reported
    as a mistake they can fix, so anything empty arriving here came out of
    the store — a turn the model returned without prose, which is legitimate
    when the question carries the turn on its own. The service recovers such
    a turn from the question in its payload before replaying it, so reaching
    this line means the row has no content anywhere and there is nothing to
    replay but a blank.

    Raising instead would wedge the session permanently: the same row is
    replayed on every later turn and would fail identically each time,
    leaving an interview that can no longer be answered, resumed, or
    completed, with no way for the manager to recover it.
    """
    if not isinstance(history, list):
        raise AgentError("היסטוריית הראיון אינה תקינה")
    clean = []
    for message in history:
        if not isinstance(message, dict):
            raise AgentError("הודעה בראיון אינה תקינה")
        role = message.get("role")
        content = message.get("content")
        if role not in ("assistant", "user") or not isinstance(content, str):
            raise AgentError("הודעה בראיון אינה תקינה")
        content = content.strip()
        if not content:
            continue
        clean.append({"role": role, "content": content[:_MAX_MESSAGE_CHARS]})
    return clean[-_MAX_MESSAGES:]


def _lines(value) -> List[str]:
    if not isinstance(value, list):
        return []
    lines = [_bounded(item) for item in value]
    return [line for line in lines if line]


def _bounded(value, limit: int = _MAX_MESSAGE_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def empty_draft() -> dict:
    """A profile with every field present and nothing filled in.

    The first turn is rendered before the model has said anything, so the
    summary panel needs a draft of the right shape to render empty.
    """
    return _merged_draft({}, {})


__all__ = [
    "INTERVIEW_RESPONSE_SCHEMA", "INTERVIEW_TOPICS", "IntroInterview",
    "empty_draft",
]
