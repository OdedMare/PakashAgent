"""Bounding and deduplicating the prose a turn carries."""

from typing import List

MAX_MESSAGE_CHARS = 4000
MAX_TEXT_CHARS = 20000


def bounded(value, limit: int = MAX_MESSAGE_CHARS) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def lines(value) -> List[str]:
    if not isinstance(value, list):
        return []
    return [line for line in (bounded(item) for item in value) if line]


def unique(items: List[str]) -> List[str]:
    """The same lines with later repeats dropped, first occurrence winning.

    Order is preserved deliberately: these lists are read top to bottom in
    the panel beside the conversation, and the agent's own ordering carries
    its sense of what matters most. Compared on the exact string, since the
    duplicates being removed are verbatim echoes, not paraphrases.
    """
    seen, found = set(), []
    for line in items:
        if line not in seen:
            seen.add(line)
            found.append(line)
    return found
