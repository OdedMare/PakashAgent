"""Reading a competence sentence: who, and to which level or which way.

Keyword matching against the workspace's own roster, like `bl/intent/`.
It never guesses: no "רמה מקצועית" (or the older "כשירות") in the
sentence, or nobody from the roster named, and it returns None.
"""

import re
from typing import List, Optional

from app.bl.profile_service.roster import COMPETENCE_LEVELS

LEVELS = COMPETENCE_LEVELS
LABELS = {"weak": "חלשה", "medium": "בינונית", "high": "גבוהה", "excellent": "מצטיינת", "": "לא מוגדרת"}

# Each level's Hebrew words; one attached prefix (ל, ה, ב, ו) is grammar.
_WORDS = {
    "weak": ("חלש", "חלשה", "נמוך", "נמוכה"),
    "medium": ("בינוני", "בינונית"),
    "high": ("גבוה", "גבוהה"),
    "excellent": ("מצטיין", "מצטיינת", "מצוין", "מצוינת", "מצויין", "מצויינת", "ציוני", "ציונית"),
}
_UP = ("תעלה", "תעלי", "העלה", "להעלות", "העלאה", "תשדרג", "לשדרג", "שדרג")
_DOWN = ("תוריד", "תורידי", "הורד", "להוריד", "הורדה")
_CLEAR = ("תבטל", "בטל", "לבטל", "תמחק", "מחק", "למחוק", "תסיר", "הסר", "להסיר", "תאפס", "אפס", "לאפס")


# A question about competence is answered, not acted on: the model takes it.
_QUESTION = re.compile(r"\?|(?<![א-ת])(?:מה|מי|האם|איזה|איזו|אילו|למה|כמה|מתי)(?![א-ת])")


# "רמה מקצועית" is the field's name on screen; "כשירות" is what it was called
# before, and managers still say it.
_TOPIC = re.compile(r"כשיר|רמ(?:ה|ת|תו|תה)\s+(?:ה)?מקצועי")


def mentions(text: str) -> bool:
    return bool(_TOPIC.search(text or "")) and not _QUESTION.search(text or "")


def read(text: str, roster: List[str]) -> Optional[dict]:
    """{"names", "level"} for a stated level ("" clears it), or
    {"names", "step"} for one level up (+1) or down (-1); None otherwise."""
    if not mentions(text):
        return None
    names = named(text, roster)
    if not names:
        return None
    level = level_in(text)
    if level is not None:
        return dict(names=names, level=level)
    if _has(text, _CLEAR):
        return dict(names=names, level="")
    up, down = _has(text, _UP), _has(text, _DOWN)
    if up == down:
        return None
    return dict(names=names, step=1 if up else -1)


def level_in(text: str) -> Optional[str]:
    """The one level the sentence names, or None for none or several."""
    found = [level for level, words in _WORDS.items() if _has(text, words)]
    return found[0] if len(found) == 1 else None


def named(text: str, roster: List[str]) -> List[str]:
    """Every roster member named, longest name first and cut out once found,
    so "דנה כהן" does not also count as "דנה"."""
    found, rest = [], text
    for name in sorted({name for name in roster if name}, key=len, reverse=True):
        if re.search(r"(?<![א-ת])[ובלהמש]?%s(?![א-ת])" % re.escape(name), rest):
            found.append(name)
            rest = rest.replace(name, " ")
    return [name for name in roster if name in found]


def shifted(current: str, step: int) -> Optional[str]:
    """One level up or down; None when there is no level to move from, or
    no level past the end."""
    if current not in LEVELS:
        return None
    position = LEVELS.index(current) + step
    return LEVELS[position] if 0 <= position < len(LEVELS) else None


def _has(text: str, words) -> bool:
    return any(re.search(r"(?<![א-ת])[ולהב]?%s(?![א-ת])" % re.escape(word), text) for word in words)
