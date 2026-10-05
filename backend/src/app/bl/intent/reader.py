"""`read()`: what a sentence is asking for, as far as code can tell."""

from typing import Any, List, Optional

from app.bl.intent.dates import date_in
from app.bl.intent.vocabulary import (
    ABSENCE_WORDS, EMPLOYEE_WORDS, GAP_WORDS, INTENT_ABSENCE, INTENT_EMPLOYEE,
    INTENT_GAPS, INTENT_PERIOD, INTENT_PUBLISH, INTENT_REPLACEMENTS,
    INTENT_TEAM, INTENT_UNKNOWN, MAX_TEXT_CHARS, PERIOD_WORDS, PUBLISH_WORDS,
    REPLACEMENT_WORDS, TEAM_WORDS,
)

# (intent, phrases, needs a named employee). **Order is the decision.**
# Publish before gaps: "מה חסר לפני פרסום" contains "מה חסר", and a bare gap
# search would drop the pending requests and warnings. Absence before
# replacement: "דנה חולה, מי יכול להחליף" is both, and the absence reading
# carries the extra fact that somebody is unavailable.
_RULES = (
    (INTENT_PUBLISH, PUBLISH_WORDS, False),
    (INTENT_ABSENCE, ABSENCE_WORDS, True),
    (INTENT_REPLACEMENTS, REPLACEMENT_WORDS, False),
    (INTENT_GAPS, GAP_WORDS, False),
    (INTENT_EMPLOYEE, EMPLOYEE_WORDS, True),
    (INTENT_TEAM, TEAM_WORDS, False),
    (INTENT_PERIOD, PERIOD_WORDS, False),
)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def read(
    request: str,
    roster: Optional[List[str]] = None,
    shift_names: Optional[List[str]] = None,
    today: Optional[str] = None,
    period: Optional[dict] = None,
) -> dict:
    """What a sentence is asking for, as far as code can tell.

    `roster` and `shift_names` are the names this workspace declared;
    matching against them is what stops "המשמרת" from becoming a person.
    `period` is what a weekday name resolves against. Always a dict: an
    unreadable sentence is `INTENT_UNKNOWN` with `confident: False` -- never a
    guess and never an exception.
    """
    text = request.strip()[:MAX_TEXT_CHARS] if isinstance(request, str) else ""
    if not text:
        return _unknown("")
    employee = first_named(text, [_text(n) for n in roster or [] if _text(n)])
    intent = classify(text, employee)
    return {
        "intent": intent,
        # Whether the sentence was placed rather than defaulted to: "I read
        # this as…" and "I did not understand" are different things to say.
        "confident": intent != INTENT_UNKNOWN,
        "employee": employee,
        "shift": first_named(text, [_text(n) for n in shift_names or [] if _text(n)]),
        "date": date_in(text, today=today, period=period),
        "request": text,
    }


def classify(text: str, employee: str) -> str:
    """Which question this is: the first rule whose phrases appear."""
    for intent, phrases, needs_employee in _RULES:
        if needs_employee and not employee:
            continue
        if any(phrase in text for phrase in phrases):
            return intent
    return INTENT_UNKNOWN


def first_named(text: str, names: List[str]) -> str:
    """The first declared name the sentence contains, longest first.

    Longest first, so "דנה כהן" wins over its prefix "דנה". Only declared
    names: a name is a person (or a shift, D9) because the workspace said so.
    """
    for name in sorted(names, key=len, reverse=True):
        if name and name in text:
            return name
    return ""


def _unknown(text: str) -> dict:
    return {
        "intent": INTENT_UNKNOWN, "confident": False,
        "employee": "", "shift": "", "date": "", "request": text,
    }
