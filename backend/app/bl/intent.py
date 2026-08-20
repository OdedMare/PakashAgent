"""Reading a manager's sentence without a model.

**Pure Python. No LLM call, ever.** This is the floor the product stands on
when no model is configured, when the model is down, and when it is too slow
to wait for — and `README.md`'s promise that the product works without an LLM
is the reason it exists.

## What this is and is not

It is **not** a second `ChangeAgent`. It does not decide who should replace
whom, it does not write Hebrew explanations of its judgment, and it never
produces an operation to apply. What it does is far smaller and entirely
mechanical: given *"מי יכול להחליף את יוסי בשבת"*, work out that the manager
is asking for **replacements**, that the person is **יוסי**, and that the day
is **Saturday** — then hand those to `bl/tools.py`, which answers with
arithmetic.

That split is the same one running through the whole codebase
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)):
the model is for judgment and phrasing, code is for counting. Matching a
handful of Hebrew keywords against a roster the workspace already declared is
not judgment. It is a lookup, and a lookup is something code can do honestly.

**What is lost without the model is real and is not hidden.** A deterministic
read of a sentence handles the shapes below and nothing else; anything it
cannot place comes back as `INTENT_UNKNOWN` and the caller says plainly that
it did not understand, rather than guessing. Guessing is the failure this
module must not have: an agent that acts on a misread sentence with no model
to blame is worse than one that asks.

## The shapes it reads

- **replacements** — *"מי יכול להחליף את X"*, *"מחליף ל-X"*
- **absence** — *"X חולה ביום חמישי"*, *"X בחופש"* — read as a request for
  replacements for that person on that day, because that is what a manager
  saying it wants next.
- **gaps** — *"מה חסר"*, *"איפה חסרים אנשים"*, *"משמרות ריקות"*
- **employee** — *"מה יש ל-X"*, *"כמה שעות יש ל-X"*
- **publish readiness** — *"מה חסר לפני פרסום"*, *"אפשר לפרסם"*
- **period** — *"מה יש השבוע"*, *"תראה לי את השבוע"*

Names come from the roster, never from the sentence's own shape: a token is
an employee because the workplace declared it, which is what stops a
misspelled word from becoming a person. Dates come from Hebrew weekday names
and from `היום`/`מחר`/`אתמול`, resolved against the period being asked about
rather than against the server's clock where a period is known.
"""

import datetime
import re
from typing import Any, Dict, List, Optional

# What the manager was asking for. Each maps to one or two `bl/tools.py`
# calls -- the mapping lives in the service, because which period a tool
# should read is a question about stored state rather than about the words.
INTENT_REPLACEMENTS = "replacements"
INTENT_ABSENCE = "absence"
INTENT_GAPS = "gaps"
INTENT_EMPLOYEE = "employee"
INTENT_PUBLISH = "publish_readiness"
INTENT_PERIOD = "period"
INTENT_UNKNOWN = "unknown"

# Hebrew weekdays as the product writes them everywhere else -- the interview
# collects them, `audit.py` prints them, the source files use them. Sunday is
# index 0 because the Israeli week runs ראשון through שבת, the same basis
# `week_bounds()` and `useBoard.sundayOf()` are built on.
_WEEKDAYS = {
    "ראשון": 0, "יום ראשון": 0, "א'": 0,
    "שני": 1, "יום שני": 1, "ב'": 1,
    "שלישי": 2, "יום שלישי": 2, "ג'": 2,
    "רביעי": 3, "יום רביעי": 3, "ד'": 3,
    "חמישי": 4, "יום חמישי": 4, "ה'": 4,
    "שישי": 5, "יום שישי": 5, "ו'": 5,
    "שבת": 6, "יום שבת": 6, "ש'": 6,
}

# Phrases that say the manager wants somebody else on a shift.
_REPLACEMENT_WORDS = (
    "מי יכול להחליף", "מי יכולה להחליף", "להחליף את", "מחליף ל",
    "מחליפה ל", "מי מחליף", "מי מחליפה", "החלפה ל", "מי פנוי", "מי פנויה",
    "מי יכול לקחת", "כיסוי ל", "למצוא כיסוי", "תמצא כיסוי",
)

# Phrases that say somebody is not coming. Read as "find replacements",
# because a manager who says דנה is sick is telling you about a hole.
_ABSENCE_WORDS = (
    "חולה", "חולות", "בחופש", "בחופשה", "לא מגיע", "לא מגיעה",
    "לא יכול", "לא יכולה", "לא זמין", "לא זמינה", "מילואים", "חופש",
)

# Phrases asking what is unstaffed.
_GAP_WORDS = (
    "מה חסר", "מי חסר", "חסרים", "חסרות", "משמרות ריקות", "ריקות",
    "לא מאויש", "לא מאוישות", "חורים בסידור", "פערים", "כיסוי",
)

# Phrases asking whether the period can go out to the team.
_PUBLISH_WORDS = (
    "לפני פרסום", "לפני שאני מפרסם", "לפני שנפרסם", "אפשר לפרסם",
    "מוכן לפרסום", "מוכנה לפרסום", "לפרסם",
)

# Phrases asking to see the period itself.
_PERIOD_WORDS = (
    "מה יש השבוע", "תראה לי את השבוע", "איך נראה השבוע", "הסידור של השבוע",
    "מה הסידור", "תראה את הסידור", "הסידור הנוכחי",
)

# Phrases asking about one person's own week.
_EMPLOYEE_WORDS = (
    "כמה שעות", "מה יש ל", "מתי עובד", "מתי עובדת", "המשמרות של",
    "השעות של", "מה המצב של",
)

_MAX_TEXT_CHARS = 500


def read(
    request: str,
    roster: Optional[List[str]] = None,
    shift_names: Optional[List[str]] = None,
    today: Optional[str] = None,
    period: Optional[dict] = None,
) -> dict:
    """What a sentence is asking for, as far as code can tell.

    `roster` and `shift_names` come from the workplace profile — the names
    this workspace actually declared. Matching against them rather than
    guessing from word shape is what stops *"מי יכול להחליף את המשמרת"* from
    deciding "המשמרת" is a person.

    `period` is the schedule the question is about, when one is known. Its
    bounds are what a weekday name resolves against, so *"בשבת"* asked while
    looking at next week means *that* Saturday rather than the one after
    today. Falling back to the clock is right only when no period is open.

    Always returns a dict. An unreadable sentence is `INTENT_UNKNOWN` with
    `confident: False` — never a guess, and never an exception, because the
    caller's job is to say "לא הבנתי" and offer what it *can* do.
    """
    text = _bounded(request)
    if not text:
        return _unknown("")

    roster = [_text(name) for name in (roster or []) if _text(name)]
    shift_names = [_text(name) for name in (shift_names or []) if _text(name)]

    employee = _employee_in(text, roster)
    shift = _shift_in(text, shift_names)
    date = _date_in(text, today=today, period=period)

    intent = _classify(text, employee)

    return {
        "intent": intent,
        # Whether the sentence was actually placed rather than defaulted to.
        # The caller renders a different opening line for each, because "I
        # read this as a request for replacements" and "I did not understand"
        # are different things to say.
        "confident": intent != INTENT_UNKNOWN,
        "employee": employee,
        "shift": shift,
        "date": date,
        "request": text,
    }


def _classify(text: str, employee: str) -> str:
    """Which question this is. Order matters and is the decision.

    Absence is tested before replacement because *"דנה חולה, מי יכול
    להחליף"* is both, and the absence reading carries the extra fact — that
    somebody should also be recorded as unavailable — which the replacement
    reading would throw away.

    Publish is tested before gaps because *"מה חסר לפני פרסום"* contains
    "מה חסר", and answering it as a bare gap search would drop the pending
    requests and the warnings that are the rest of that question.
    """
    if _any_in(text, _PUBLISH_WORDS):
        return INTENT_PUBLISH
    if employee and _any_in(text, _ABSENCE_WORDS):
        return INTENT_ABSENCE
    if _any_in(text, _REPLACEMENT_WORDS):
        return INTENT_REPLACEMENTS
    if _any_in(text, _GAP_WORDS):
        return INTENT_GAPS
    if employee and _any_in(text, _EMPLOYEE_WORDS):
        return INTENT_EMPLOYEE
    if _any_in(text, _PERIOD_WORDS):
        return INTENT_PERIOD
    return INTENT_UNKNOWN


def _employee_in(text: str, roster: List[str]) -> str:
    """The first roster name the sentence contains.

    Longest first, so a roster holding both "דנה" and "דנה כהן" matches the
    fuller name rather than the prefix of it. Matching against the declared
    roster is the whole safeguard here: a name is a person because the
    workspace said so, never because it looked like one.
    """
    for name in sorted(roster, key=len, reverse=True):
        if name and name in text:
            return name
    return ""


def _shift_in(text: str, shift_names: List[str]) -> str:
    """The first declared shift name the sentence contains.

    From the profile's vocabulary only (D9). There is no fallback list of
    shift names here and there must not be one — a workplace's shifts are
    whatever it declared, and a literal here would be the hardcoding D9
    forbids.
    """
    for name in sorted(shift_names, key=len, reverse=True):
        if name and name in text:
            return name
    return ""


def _date_in(
    text: str,
    today: Optional[str] = None,
    period: Optional[dict] = None,
) -> str:
    """The date the sentence means, ISO, or empty when it names none.

    Three sources, in order of how specific they are: an explicit date, a
    relative word (`היום`, `מחר`, `מחרתיים`, `אתמול`), and a Hebrew weekday
    resolved inside the open period.
    """
    explicit = _explicit_date(text)
    if explicit:
        return explicit

    anchor = _parse(today) or datetime.date.today()

    if "מחרתיים" in text:
        return (anchor + datetime.timedelta(days=2)).isoformat()
    if "מחר" in text:
        return (anchor + datetime.timedelta(days=1)).isoformat()
    if "אתמול" in text:
        return (anchor - datetime.timedelta(days=1)).isoformat()
    if "היום" in text:
        return anchor.isoformat()

    return _weekday_in(text, anchor, period)


def _weekday_in(
    text: str, anchor: datetime.date, period: Optional[dict]
) -> str:
    """A Hebrew weekday, resolved against the open period where there is one.

    Inside a period, *"בשבת"* means that period's Saturday — the manager is
    looking at a week and talking about a day in it. With no period open it
    means the next such day from today, which is what the word means in
    ordinary speech.

    Longest-first again, so "יום ראשון" is not matched as "ראשון" inside a
    different phrase.
    """
    found = None
    for label in sorted(_WEEKDAYS, key=len, reverse=True):
        if label in text:
            found = _WEEKDAYS[label]
            break
    if found is None:
        return ""

    starts = _parse(_iso((period or {}).get("starts_on")))
    ends = _parse(_iso((period or {}).get("ends_on")))
    if starts and ends:
        day = starts
        while day <= ends:
            # `weekday()` is Monday-based; `(weekday() + 1) % 7` shifts it to
            # the Sunday-based index the rest of the product uses.
            if (day.weekday() + 1) % 7 == found:
                return day.isoformat()
            day += datetime.timedelta(days=1)
        return ""

    ahead = (found - (anchor.weekday() + 1) % 7) % 7
    return (anchor + datetime.timedelta(days=ahead)).isoformat()


def _explicit_date(text: str) -> str:
    """A date written out, as ISO or as `d/m` / `d.m` / `d/m/yy`.

    The formats the real source files use (`FILE_FORMATS.md`) plus ISO, which
    is what the API speaks. A two-digit year is read as 2000-based; a missing
    year takes the current one, because a manager writing "12.6" means this
    year and writing the year out is what they do when they do not.
    """
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if iso:
        try:
            return datetime.date(
                int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
            ).isoformat()
        except ValueError:
            return ""

    short = re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", text)
    if short:
        day, month, year = short.group(1), short.group(2), short.group(3)
        value = int(year) if year else datetime.date.today().year
        if value < 100:
            value += 2000
        try:
            return datetime.date(value, int(month), int(day)).isoformat()
        except ValueError:
            return ""

    return ""


def _unknown(text: str) -> dict:
    return {
        "intent": INTENT_UNKNOWN,
        "confident": False,
        "employee": "",
        "shift": "",
        "date": "",
        "request": text,
    }


def _any_in(text: str, phrases: tuple) -> bool:
    return any(phrase in text for phrase in phrases)


def _parse(value: Optional[str]) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(value or "")
    except (ValueError, TypeError):
        return None


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _text(value)


def _bounded(value: Any) -> str:
    return value.strip()[:_MAX_TEXT_CHARS] if isinstance(value, str) else ""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "read",
    "INTENT_REPLACEMENTS",
    "INTENT_ABSENCE",
    "INTENT_GAPS",
    "INTENT_EMPLOYEE",
    "INTENT_PUBLISH",
    "INTENT_PERIOD",
    "INTENT_UNKNOWN",
]
