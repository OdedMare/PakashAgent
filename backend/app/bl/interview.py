"""Model-driven intro interview, one Hebrew question per turn."""

import json
from typing import Dict, List

from app.bl.prompts import load
from app.common.errors import AgentError


# The boss's questions plus the missing inputs the scheduler and audit need.
# The model may skip a topic already answered elsewhere, but may not complete
# until every topic is covered and the final summary is confirmed.
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

_OPTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "label", "recommended"],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z0-9_]+$"},
        "label": {"type": "string"},
        "recommended": {"type": "boolean"},
    },
}

INTERVIEW_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status", "question_id", "question", "recommendation", "options",
        "allow_free_text", "profile",
    ],
    "properties": {
        "status": {"type": "string", "enum": ["question", "complete"]},
        "question_id": {"type": ["string", "null"]},
        "question": {"type": ["string", "null"]},
        "recommendation": {"type": ["string", "null"]},
        "options": {
            "type": "array", "items": _OPTION_SCHEMA, "maxItems": 5,
        },
        "allow_free_text": {"type": "boolean"},
        "profile": {"oneOf": [_PROFILE_SCHEMA, {"type": "null"}]},
    },
}


class IntroInterview:
    """Ask the next question or return the confirmed workplace profile.

    The caller owns persistence and passes the conversation back on every
    turn. Keeping this service stateless avoids inventing a session store
    before the repository layer exists.
    """

    def __init__(self, llm):
        self._llm = llm
        self._system_prompt = load("interview")

    def next_turn(self, history: List[Dict[str, str]]) -> dict:
        conversation = _validated_history(history)
        response = self._llm.complete_json(
            self._system_prompt,
            json.dumps(
                {"topics": INTERVIEW_TOPICS, "conversation": conversation},
                ensure_ascii=False,
            ),
            schema=INTERVIEW_RESPONSE_SCHEMA,
        )
        return _validated_response(response)


def _validated_history(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
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
            raise AgentError("הודעה בראיון אינה יכולה להיות ריקה")
        clean.append({"role": role, "content": content})
    return clean


def _validated_response(response: dict) -> dict:
    if not isinstance(response, dict):
        raise AgentError("המודל החזיר תוצאת ראיון לא תקינה")
    result = dict(response)
    usage = result.pop("_usage", None)
    status = result.get("status")
    if status == "question":
        required = ("question_id", "question", "recommendation")
        if any(not isinstance(result.get(key), str) or not result[key].strip()
               for key in required):
            raise AgentError("המודל החזיר שאלת ראיון לא תקינה")
        if result.get("profile") is not None:
            raise AgentError("המודל החזיר פרופיל לפני סיום הראיון")
        _validate_options(result.get("options"))
        if result.get("allow_free_text") is not True:
            raise AgentError("שאלת ראיון חייבת לאפשר תשובה חופשית")
    elif status == "complete":
        if any(result.get(key) is not None
               for key in ("question_id", "question", "recommendation")):
            raise AgentError("המודל סיים את הראיון עם שאלה פתוחה")
        if result.get("options") != [] or result.get("allow_free_text") is not False:
            raise AgentError("המודל סיים את הראיון עם אפשרויות פתוחות")
        profile = result.get("profile")
        required = set(_PROFILE_SCHEMA["required"])
        if not isinstance(profile, dict) or not required.issubset(profile):
            raise AgentError("המודל החזיר פרופיל מקום עבודה חסר")
    else:
        raise AgentError("המודל החזיר סטטוס ראיון לא תקין")
    if usage is not None:
        result["_usage"] = usage
    return result


def _validate_options(options) -> None:
    if not isinstance(options, list) or not 2 <= len(options) <= 5:
        raise AgentError("שאלת ראיון חייבת לכלול בין 2 ל-5 אפשרויות")
    identifiers = set()
    recommended = 0
    for option in options:
        if not isinstance(option, dict):
            raise AgentError("אפשרות תשובה בראיון אינה תקינה")
        option_id = option.get("id")
        label = option.get("label")
        is_recommended = option.get("recommended")
        if (not isinstance(option_id, str) or not option_id
                or not isinstance(label, str) or not label.strip()
                or not isinstance(is_recommended, bool)):
            raise AgentError("אפשרות תשובה בראיון אינה תקינה")
        if option_id in identifiers:
            raise AgentError("אפשרויות התשובה בראיון חייבות להיות ייחודיות")
        identifiers.add(option_id)
        recommended += int(is_recommended)
    if recommended > 1:
        raise AgentError("רק אפשרות אחת יכולה להיות מומלצת")
