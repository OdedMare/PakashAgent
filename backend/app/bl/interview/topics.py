"""The nine core topics, and recognising a question already put."""

import copy
import difflib
import re
from typing import List, Optional

from app.bl.interview.text import bounded

INTERVIEW_TOPICS = (
    {
        "id": "workplace_and_cycle",
        "question": "מה שם היחידה ומה מבנה היציאות הכללי, ובכל סבב או תלתון פעיל איזו קבוצה סוגרת באיזה סוף שבוע עוגן?",
    },
    {
        "id": "operating_calendar",
        "question": "באילו ימים ושעות מקום העבודה פעיל, והאם יש ימים חריגים?",
    },
    {
        "id": "shift_vocabulary",
        "question": "מהם סוגי המשמרות, מהן השעות, האם זו משמרת רגילה, חפיפה או כוננות, ומה התקן בכל אחת?",
    },
    {
        "id": "staffing",
        "question": "כמה עובדים ואילו תפקידים חייבים להיות בכל משמרת, והאם התקן משתנה לפי יום?",
    },
    {
        "id": "roster",
        "question": "מי אנשי הצוות: שם, תפקיד, מבנה יציאות אישי (סבב, תלתון, חמשושים או שושים), מעמד, יכולת פיקוד וחפיפה ואילו משמרות הם יכולים לבצע?",
    },
    {
        "id": "constraints",
        "question": "אילו אילוצים קבועים חוזרים ואילו אילוצים זמניים יש, ועד מתי מגישים אותם?",
    },
    {
        "id": "rest_policy",
        "question": "מה כללי המנוחה בין משמרות, רצף ימי עבודה, לילות וסופי שבוע?",
    },
    {
        "id": "special_cases",
        "question": "האם יש כוננים, מתלמדים, עובדים מזדמנים או מנהלים שמשובצים, ואיך סופרים אותם?",
    },
    {
        "id": "priorities",
        "question": "כשיש התנגשות, מה קודם למה ואיך תרצה לחלק עומס, לילות וסופי שבוע?",
    },
)

CORE_TOPIC_IDS = tuple(item["id"] for item in INTERVIEW_TOPICS)
CONTINUE_TOPIC_ID = "continue_optional"
OPTIONAL_TOPIC_ID = "optional_follow_up"
CONTINUE_ANSWER = "כן, אפשר להמשיך לכמה שאלות העמקה קצרות."
FINISH_ANSWER = "לא, מספיק לי. אפשר לעבור לסיכום ולאישור."

_CONTINUE_QUESTION = {
    "topic_id": CONTINUE_TOPIC_ID,
    "question": "סיימנו את שאלות החובה. להמשיך לכמה שאלות העמקה אופציונליות?",
    "recommendation": "אם זה הסידור הראשון שלך במערכת, כדאי לעבור לסיכום ולהתחיל לעבוד.",
    "why": "פרטים נוספים אפשר ללמד אחר כך מתוך תיקונים אמיתיים, בלי להאריך את ההקמה.",
    "options": [
        {"label": "לעבור לסיכום", "answer": FINISH_ANSWER},
        {"label": "להמשיך להעמקה", "answer": CONTINUE_ANSWER},
    ],
}

_QUESTION_STOP_WORDS = frozenset({
    "איך", "אילו", "איזה", "האם", "מה", "מי", "של", "את", "על", "עם",
    "בכל", "כל", "יש", "כמה", "ומה", "הם", "היא", "הוא",
})
_SIMILAR_WORDING = 0.76
_SHARED_WORDS = 0.75


def continue_question() -> dict:
    return copy.deepcopy(_CONTINUE_QUESTION)


def topic_question(topic_id: str) -> dict:
    topic = next(item for item in INTERVIEW_TOPICS if item["id"] == topic_id)
    return _plain_question(topic)


def next_topic_question(asked) -> Optional[dict]:
    """A deterministic escape hatch when a model forgets to ask anything."""
    asked = [bounded(item) for item in asked or [] if bounded(item)]
    topic = next(
        (item for item in INTERVIEW_TOPICS
         if not already_asked(item["question"], asked)),
        None,
    )
    return _plain_question(topic) if topic is not None else None


def _plain_question(topic: dict) -> dict:
    return {
        "topic_id": topic["id"],
        "question": topic["question"],
        "recommendation": "",
        "why": "",
        "options": [],
    }


def already_asked(question: str, asked: List[str]) -> bool:
    """Exact or near-identical wording that the manager already saw."""
    current = _question_words(question)
    if not current:
        return False
    current_text, current_set = " ".join(current), set(current)
    for previous in asked:
        words = _question_words(previous)
        if not words:
            continue
        if difflib.SequenceMatcher(
            None, current_text, " ".join(words)
        ).ratio() >= _SIMILAR_WORDING:
            return True
        shared = current_set.intersection(words)
        if len(shared) >= 2 and len(shared) / min(
            len(current_set), len(set(words))
        ) >= _SHARED_WORDS:
            return True
    return False


def _question_words(value: str) -> List[str]:
    words = re.findall(r"[\w֐-׿]+", bounded(value).lower())
    return [word for word in words if word not in _QUESTION_STOP_WORDS]
