"""The draft profile: merged across turns, and what it still owes."""

from typing import Any, Dict, List

from app.bl.interview.profile_schema import (
    LIST_FIELDS, OBJECT_FIELDS, TEXT_FIELDS,
)
from app.bl.interview.text import MAX_TEXT_CHARS, as_dict, bounded

# What `ready` requires beyond the model's own say-so. These are the fields
# the scheduler cannot run without: a profile missing one is not a finished
# interview whatever the model claimed.
_REQUIRED_TOPICS = (
    ("workplace", "name", "חסר שם למקום העבודה."),
    ("workplace", "planning_horizon", "חסרה תקופת התכנון של הסידור."),
)
_REQUIRED_NUMERIC_TOPICS = (
    ("audit_policy", "max_weekly_hours", "חסרה תקרת שעות שבועית."),
    ("audit_policy", "max_consecutive_days", "חסר מספר ימי העבודה הרצופים המרבי."),
    ("audit_policy", "min_rest_hours", "חסר זמן המנוחה המזערי בין משמרות."),
)


def merged_draft(offered, previous) -> dict:
    """This turn's draft over the last, so nothing agreed is dropped.

    The model rebuilds the draft from scratch every turn, and a turn that
    answers a narrow question by re-emitting only the field it touched would
    otherwise blank the twenty fields it did not — precisely at the
    confirmation turn. A field is carried forward only when this turn left it
    empty, so the model can still correct any value by restating it.
    """
    offered, previous = as_dict(offered), as_dict(previous)
    merged: Dict[str, Any] = {}
    for field in TEXT_FIELDS:
        merged[field] = (
            bounded(offered.get(field), MAX_TEXT_CHARS)
            or bounded(previous.get(field), MAX_TEXT_CHARS)
        )
    for field in LIST_FIELDS:
        value = offered.get(field)
        if not isinstance(value, list) or not value:
            value = previous.get(field)
        merged[field] = value if isinstance(value, list) else []
    for field in OBJECT_FIELDS:
        # Merged per key rather than whole: `workplace` holds eight fields
        # settled across different turns.
        merged[field] = dict(as_dict(previous.get(field)), **{
            key: item for key, item in as_dict(offered.get(field)).items()
            if item != "" and item != [] and item is not None
        })
    return merged


def missing_topics(draft: dict) -> List[str]:
    """One line per required field the draft still owes.

    Public because the readiness gate, `interview_service.end` and
    `bl/tools.py` all need the same answer, and a second copy of these rules
    would drift into an agent describing a gap the gate does not see.
    """
    missing = [
        message for section, field, message in _REQUIRED_TOPICS
        if not bounded(as_dict(draft.get(section)).get(field))
    ]
    for section, field, message in _REQUIRED_NUMERIC_TOPICS:
        value = as_dict(draft.get(section)).get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            missing.append(message)
    if not draft.get("shifts"):
        missing.append("לא הוגדר אף סוג משמרת.")
    if not draft.get("employees"):
        missing.append("לא נרשם אף עובד.")
    return missing


def empty_draft() -> dict:
    """A profile with every field present and nothing filled in.

    The first turn is rendered before the model has said anything, so the
    summary panel needs a draft of the right shape to render empty.
    """
    return merged_draft({}, {})
