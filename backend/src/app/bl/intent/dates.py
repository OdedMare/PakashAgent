"""Which date a sentence means: explicit, relative, or a weekday in the period."""

import datetime
import re
from typing import Any, Optional

from app.bl.intent.vocabulary import WEEKDAYS
from app.common.time_context import israel_today

_RELATIVE = (("מחרתיים", 2), ("מחר", 1), ("אתמול", -1), ("היום", 0))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _text(value)


def parse(value: Optional[str]) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(value or "")
    except (ValueError, TypeError):
        return None


def date_in(text: str, today: Optional[str] = None, period: Optional[dict] = None) -> str:
    """The date the sentence means, ISO, or empty when it names none.

    Three sources, most specific first: an explicit date, a relative word
    (`היום`, `מחר`, `מחרתיים`, `אתמול`), and a Hebrew weekday resolved inside
    the open period. `מחרתיים` is tested before `מחר`, which it contains.
    """
    anchor = parse(today) or israel_today()
    explicit = explicit_date(text, anchor)
    if explicit:
        return explicit
    for word, offset in _RELATIVE:
        if word in text:
            return (anchor + datetime.timedelta(days=offset)).isoformat()
    return weekday_in(text, anchor, period)


def weekday_in(text: str, anchor: datetime.date, period: Optional[dict]) -> str:
    """A Hebrew weekday, resolved against the open period where there is one.

    Inside a period, *"בשבת"* means that period's Saturday; with no period it
    means the next such day from today. Longest label first, so "יום ראשון"
    is not matched as "ראשון" inside a different phrase.
    """
    found = next(
        (WEEKDAYS[label] for label in sorted(WEEKDAYS, key=len, reverse=True) if label in text),
        None,
    )
    if found is None:
        return ""
    starts = parse(_iso((period or {}).get("starts_on")))
    ends = parse(_iso((period or {}).get("ends_on")))
    if starts and ends:
        day = starts
        while day <= ends:
            # `(weekday() + 1) % 7` is the Sunday-based index the product uses.
            if (day.weekday() + 1) % 7 == found:
                return day.isoformat()
            day += datetime.timedelta(days=1)
        return ""
    ahead = (found - (anchor.weekday() + 1) % 7) % 7
    return (anchor + datetime.timedelta(days=ahead)).isoformat()


def explicit_date(text: str, anchor: datetime.date) -> str:
    """A date written out, as ISO or as `d/m` / `d.m` / `d/m/yy`.

    A two-digit year is 2000-based; a missing year takes the current one,
    because a manager writing "12.6" means this year.
    """
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if iso:
        return _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    short = re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", text)
    if short:
        year = int(short.group(3)) if short.group(3) else anchor.year
        if year < 100:
            year += 2000
        return _safe_date(year, int(short.group(2)), int(short.group(1)))
    return ""


def _safe_date(year: int, month: int, day: int) -> str:
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return ""
