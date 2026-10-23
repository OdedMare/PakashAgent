"""Whether a sentence reports one person's absence, and for which dates.

Keyword matching against the workspace's own roster, the same move
`bl/intent/` makes, narrowed to one shape and stricter about it: the result
becomes a *plan*, so anything this cannot read with certainty is `None`
and the model takes the sentence. It never guesses a person or a date.
"""

import re
from typing import List, Optional

from app.bl.absence.dates import dates_in, only_weekdays, weekdays_named
from app.bl.absence.selections import strip_selections

# Saying somebody is away for a stretch: these carry dates or need them.
_STRONG = (
    r"חול(?:ה|ים|ות)", r"מחלה", r"בחופש(?:ה)?", r"חופש(?:ה)?", r"מילואים",
    r"טס(?:ה|ים)?", r"[בל]חו\"?ל", r"[בל]חו״ל", r"נוסע(?:ת)?\s+[לב]", r"בהשתלמות",
    r"לא\s+מגיע(?:ה)?",
)
# Saying somebody must not be placed: an absence only when dates come with it,
# since "לא יכולה לעבוד עם דנה" is a pairing wish, not a day off.
_WEAK = (
    r"לא\s+יכול(?:ה)?\s+(?:לעבוד|להגיע)", r"לא\s+זמינ?(?:ה)?", r"לא\s+זמין/ה",
    r"אל\s+תשבצ?(?:י)?", r"לא\s+לשבץ", r"אל\s+תשים", r"תוריד(?:י)?\s+אות",
    r"מהלוח", r"תחליפ?(?:י)?\s+אות",
)
_RECURRING = r"(?<![א-ת])(?:בכל|כל)\s+(?:יום\s+)?(?:ראשון|שני|שלישי|רביעי|חמישי|שישי|שבת)|בימי\s|באופן\s+קבוע|קבוע|תמיד|אף\s+פעם"
# Shapes that are not an absence report however they are worded.
_NOT_A_REPORT = r"מה\s+יקרה|(?<![א-ת])(?:ה|ו)?אם\s|כמה\s|למה\s"


def read(
    text: str, roster: List[str], shift_names: List[str],
    today: str = "", week_start: str = "",
) -> Optional[dict]:
    """`{employee, dates, scope, weekdays, request}` or `None`.

    `scope` is what to do next: `dates` (plan these days), `recurring` (a
    standing constraint on `weekdays`), `ask_dates` (one question: when?)
    or `ask_scope` (one question: this week or every week?).
    """
    request = (text or "").strip()
    sentence = strip_selections(request)
    if not sentence or re.search(_NOT_A_REPORT, sentence):
        return None
    employee = _one_employee(sentence, roster)
    strong = any(re.search(pattern, sentence) for pattern in _STRONG)
    weak = any(re.search(pattern, sentence) for pattern in _WEAK)
    if not employee or not (strong or weak):
        return None
    # A named shift narrows the absence to part of a day, which is the
    # model's to read ("אל תשבץ את עודד בלילות" is a wish, not dates).
    if any(name and name in sentence for name in shift_names):
        return None
    found = dict(employee=employee, request=request, dates=[], weekdays=[])
    if re.search(_RECURRING, sentence):
        found["weekdays"] = weekdays_named(sentence)
        return dict(found, scope="recurring") if found["weekdays"] else None
    dates = dates_in(sentence, today, week_start)
    if not dates:
        return dict(found, scope="ask_dates") if strong else None
    found["dates"] = dates
    if only_weekdays(sentence) and not strong and len(dates) == 1:
        return dict(found, scope="ask_scope", weekdays=weekdays_named(sentence))
    return dict(found, scope="dates")


def _one_employee(text: str, roster: List[str]) -> str:
    """The single roster member named, or empty for none or several.

    Longest name first, and a found name is cut out before looking further,
    so "דנה כהן" does not also count as "דנה".
    """
    found, rest = [], text
    for name in sorted({name for name in roster if name}, key=len, reverse=True):
        # One attached prefix is Hebrew grammar: "לעודד", "שירין", "ועודד".
        if re.search(r"(?<![א-ת])[ובלהמש]?%s(?![א-ת])" % re.escape(name), rest):
            found.append(name)
            rest = rest.replace(name, " ")
    return found[0] if len(found) == 1 else ""
