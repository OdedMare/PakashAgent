"""Small values shared across business-logic features."""

import datetime
from typing import Any, Optional

_MAX_TEXT_CHARS = 4000
_MAX_PREFERENCES = 40

HEBREW_WEEKDAYS = (
    "יום שני", "יום שלישי", "יום רביעי", "יום חמישי",
    "יום שישי", "שבת", "יום ראשון",
)


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def bounded(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    return text(value)[:limit]


def iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else text(value)


def parse_date(value: Any) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def number(value: Any, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    return float(value) if isinstance(value, (int, float)) else fallback


def dict_items(rows: Any) -> list[dict]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def dict_rows(rows: Any, limit: int = 200) -> list[dict]:
    return dict_items(rows)[-limit:]


def employees(profile: dict) -> list[dict]:
    return dict_items((profile or {}).get("employees"))


def shifts(profile: dict) -> list[dict]:
    return dict_items((profile or {}).get("shifts"))


def warning_key(warning: dict) -> tuple:
    return (
        text(warning.get("code")),
        text(warning.get("employee")),
        iso(warning.get("date")),
        text(warning.get("shift")),
    )


def preferences_for_model(preferences: Any) -> list[dict]:
    """A bounded projection of confirmed standing preferences."""
    return [
        {
            "kind": bounded(row.get("kind")),
            "subject": bounded(row.get("subject")),
            "text": bounded(row.get("text")),
        }
        for row in preferences or [] if isinstance(row, dict)
    ][:_MAX_PREFERENCES]


def resume(pending: str, reply: str) -> str:
    """Join a held request with the manager's clarification."""
    pending, reply = bounded(pending), bounded(reply)
    if not pending:
        return reply
    if not reply or pending in reply:
        return reply or pending
    return "%s (%s)" % (pending, reply)


def hebrew_weekday(day: Optional[datetime.date]) -> str:
    return HEBREW_WEEKDAYS[day.weekday()] if day is not None else ""


def weekday_key(value: Any) -> str:
    value = text(value)
    return value[4:].strip() if value.startswith("יום ") else value


def runs_on(days: Any, weekday: str) -> bool:
    """Whether a weekday list includes a day. Empty means every day."""
    if not isinstance(days, list) or not days:
        return True
    return weekday_key(weekday) in {weekday_key(item) for item in days}


def profile_for_model(profile: dict) -> dict:
    """The shared workplace fields used by conversational model calls."""
    profile = profile if isinstance(profile, dict) else {}
    return {
        "workplace": profile.get("workplace") or {},
        "employees": profile.get("employees") or [],
        "shifts": profile.get("shifts") or [],
        "rules": profile.get("rules") or [],
        "rest_policy": profile.get("rest_policy") or "",
        "fairness_policy": profile.get("fairness_policy") or "",
        "conflict_policy": profile.get("conflict_policy") or "",
    }
