"""Small validators every profile section shares. Errors are Hebrew."""

from typing import Any, List

from app.common.errors.errors import AgentError

_MAX_TEXT = 200


def text(value: Any) -> str:
    return value.strip()[:_MAX_TEXT] if isinstance(value, str) else ""


def text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        raise AgentError("הרשימה אינה תקינה")
    return [item for item in (text(raw) for raw in value) if item]


def valid_time(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return False
    return 0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59


def named_rows(rows: Any, label: str) -> List[dict]:
    """Rows that each carry a unique, non-empty name."""
    if not isinstance(rows, list):
        raise AgentError("הרשימה אינה תקינה")
    result, seen = [], set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise AgentError("פרטי ה%s אינם תקינים" % label)
        row = dict(raw)
        name = text(row.get("name"))
        if not name:
            raise AgentError("לכל %s חייב להיות שם" % label)
        if name in seen:
            raise AgentError("השם %s מופיע יותר מפעם אחת" % name)
        seen.add(name)
        row["name"] = name
        result.append(row)
    return result


def keep_existing_names(before: Any, after: List[dict], label: str) -> None:
    """Names are identity keys; renaming/removal needs an explicit migration."""
    old = {
        text(row.get("name")) for row in before or []
        if isinstance(row, dict) and text(row.get("name"))
    }
    missing = sorted(old - {text(row.get("name")) for row in after})
    if missing:
        raise AgentError(
            "לא ניתן לשנות או למחוק את שם ה%s %s; "
            "אפשר לערוך את שאר הפרטים או להוסיף שם חדש"
            % (label, missing[0])
        )
