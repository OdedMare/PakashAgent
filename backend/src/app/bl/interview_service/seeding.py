"""Draft states an interview starts from or ends with, beyond a blank one."""

from typing import List

from app.bl.interview import empty_draft, missing_topics

_MAX_SEED_EMPLOYEES = 500
_MAX_SEED_SHIFTS = 100
_MAX_SEED_FILES = 8


def _seed_text(value, limit: int = 120) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _seed_list(value, limit: int = 30) -> List[str]:
    if not isinstance(value, list):
        return []
    seen, result = set(), []
    for item in value:
        cleaned = _seed_text(item)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
        if len(result) == limit:
            break
    return result


def _named_rows(rows, limit: int, field: str) -> List[dict]:
    rows = rows if isinstance(rows, dict) else {}
    return [
        {"name": _seed_text(name), field: _seed_list(values)}
        for name, values in list(rows.items())[:limit] if _seed_text(name)
    ]


def _source(seed: dict) -> str:
    files = _seed_list(seed.get("source_files"), limit=_MAX_SEED_FILES)
    starts_on, ends_on = _seed_text(seed.get("starts_on"), 10), _seed_text(seed.get("ends_on"), 10)
    source = "קבצי סידור קיימים"
    if files:
        source += ": " + ", ".join(files)
    if starts_on and ends_on:
        source += " (%s עד %s)" % (starts_on, ends_on)
    return source


def seeded_state(seed: dict) -> dict:
    """A sparse draft from an imported roster; the interview verifies it."""
    seed = seed if isinstance(seed, dict) else {}
    workplace_name = _seed_text(seed.get("workplace_name"))
    employees = _named_rows(seed.get("employees"), _MAX_SEED_EMPLOYEES, "eligible_shifts")
    shifts = _named_rows(seed.get("shifts"), _MAX_SEED_SHIFTS, "days")
    draft = empty_draft()
    if workplace_name:
        draft["workplace"] = {"name": workplace_name}
    draft.update({
        "employees": employees,
        "shifts": shifts,
        "existing_schedule_source": _source(seed),
    })
    resolved, open_points = [], []
    if workplace_name:
        resolved.append("שם מקום העבודה: %s" % workplace_name)
    if employees:
        resolved.append("נמצאו %d עובדים בסידור הקיים." % len(employees))
        open_points.append("לאשר תפקידים והיקפי עבודה של העובדים שנמצאו.")
    if shifts:
        resolved.append("נמצאו %d סוגי משמרות בסידור הקיים." % len(shifts))
        open_points.append("לאשר שעות ותקינה של המשמרות שנמצאו.")
    return {
        "draft": draft,
        "resolved": resolved,
        "open_points": open_points,
        "reply": "קראתי את הסידור הקיים. עכשיו נאמת רק את מה שצריך.",
    }


def completeness(pending: dict, draft: dict) -> dict:
    """What an ended interview still owes, recorded on its own profile.

    The required topics are what the *scheduler* cannot run without; the open
    points are the agent's own list of what it has not settled. `complete:
    False` marks a profile as ended early -- one confirmed the ordinary way
    carries no such key at all.
    """
    return {
        "complete": False,
        "missing_topics": missing_topics(draft),
        "open_points": list(pending.get("open_points") or []),
        "resolved": list(pending.get("resolved") or []),
    }
