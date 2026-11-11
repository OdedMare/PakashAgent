"""Who in the roster a name written in a file means.

A sheet writes people the way the person keeping it does: "שובל ק.",
"שובל", "קרמר שובל". The roster says "שובל קרמר". Matching is code, not
the model, and it never guesses: one candidate is a match, several are a
question for the confirm screen, none is a name the manager maps or keeps.
"""

import re
from typing import Dict, Iterable, List, Optional

from app.bl.importer.cells import normalise
from app.bl.tools.roster import resolve_employee
from app.bl.tools.values import employees, text

EXACT = "exact"
MATCHED = "matched"
AMBIGUOUS = "ambiguous"
UNKNOWN = "unknown"

_PUNCTUATION = re.compile(r"[.'׳״\"`,()\[\]]+")


def match_people(names: Iterable[str], profile: Optional[dict]) -> Dict[str, dict]:
    """`{name in file: {employee, status, candidates}}` for every name."""
    roster = [text(row.get("name")) for row in employees(profile or {}) if text(row.get("name"))]
    found = {}
    for name in names:
        if name and name not in found:
            found[name] = _match(name, roster, profile or {})
    return found


def _match(name: str, roster: List[str], profile: dict) -> dict:
    if name in roster:
        return _answer(name, EXACT, [name])
    cleaned = _clean(name)
    exact = [person for person in roster if _clean(person) == cleaned]
    if len(exact) == 1:
        return _answer(exact[0], EXACT, exact)
    candidates = exact or _by_tokens(cleaned, roster)
    if not candidates:
        resolved = resolve_employee(profile, cleaned)
        candidates = list(resolved.get("matches") or [])
    if len(candidates) == 1:
        return _answer(candidates[0], MATCHED, candidates)
    if candidates:
        return _answer(None, AMBIGUOUS, candidates)
    return _answer(None, UNKNOWN, [])


def _by_tokens(cleaned: str, roster: List[str]) -> List[str]:
    """Roster names whose words the file's words abbreviate, in any order.

    "שובל ק" fits "שובל קרמר" (a word and an initial); "קרמר" alone fits
    every Kramer on the roster -- which is several, and so a question.
    """
    words = cleaned.split()
    if not words:
        return []
    found = []
    for person in roster:
        theirs = _clean(person).split()
        # Either way round: "שובל ק" abbreviates "שובל קרמר", and a roster
        # that only says "יוסי" is what the file means by "יוסי ב.".
        # The second way needs whole words: roster "דן" is not "דנה כהן".
        if _covers(words, theirs) or _covers(theirs, words, whole=True):
            found.append(person)
    return found


def _covers(words: List[str], theirs: List[str], whole: bool = False) -> bool:
    remaining = list(theirs)
    for word in words:
        hit = next((other for other in remaining
                    if other == word or (not whole and other.startswith(word))), None)
        if hit is None:
            return False
        remaining.remove(hit)
    return True


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", _PUNCTUATION.sub(" ", normalise(value))).strip()


def _answer(employee: Optional[str], status: str, candidates: List[str]) -> dict:
    return {"employee": employee, "status": status, "candidates": candidates}
