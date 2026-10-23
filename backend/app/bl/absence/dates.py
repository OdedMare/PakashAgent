"""Every date an absence sentence names: lists, ranges, weekdays, the week.

`intent.dates.date_in` answers "which one date", which is right for a
question and wrong for an absence: *"עודד חולה בשני ושלישי"* is two days, and
reading only one of them leaves the other day's shift on the board.
"""

import datetime
import re
from typing import List, Optional

from app.bl.intent.dates import parse
from app.common.time_context import israel_today

# Past a month a sentence is describing a departure or a long leave, which is
# a different plan (`retire`, or the manager's own reading of it).
MAX_DAYS = 31

_WEEKDAY_NAMES = ("ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת")
# A weekday as a whole word, allowing Hebrew's attached prefixes: בשני,
# ושלישי, מראשון, ובשבת, ועד שישי. Hebrew letters on either side mean the
# token is part of another word ("השנייה", "שבתון"), so they do not match.
_WEEKDAY = re.compile(
    r"(?<![א-ת])(?:ו?(?:ב|מ|ל|ה)?)(?:יום\s+)?(%s)(?![א-ת])"
    % "|".join(_WEEKDAY_NAMES)
)
_DATE = r"(?<!\d)(\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?)(?!\d)"
_DATE_RE = re.compile(_DATE)
# "עד", "-", "ועד ה-" or a bare "ל-" between two ends; a plain "ו" lists
# two days rather than spanning them, so it is not a connector here.
_RANGE_JOIN = r"\s*(?:(?:-|–|ועד|עד)\s*(?:ה|ל)?-?|ל-?)\s*(?:יום\s+)?"
_DATE_RANGE = re.compile(_DATE + _RANGE_JOIN + _DATE)
_WEEKDAY_RANGE = re.compile(
    r"(?<![א-ת])(?:מ|בין\s+)?(?:יום\s+)?(%s)%s(%s)(?![א-ת])"
    % ("|".join(_WEEKDAY_NAMES), _RANGE_JOIN, "|".join(_WEEKDAY_NAMES))
)
_RELATIVE = (("מחרתיים", 2), ("מחר", 1), ("היום", 0))


def week_of(day: datetime.date) -> List[datetime.date]:
    sunday = day - datetime.timedelta(days=(day.weekday() + 1) % 7)
    return [sunday + datetime.timedelta(days=offset) for offset in range(7)]


def dates_in(text: str, today: Optional[str] = None, week_start: str = "") -> List[str]:
    """Every date the sentence names, sorted ISO; empty when it names none.

    Weekdays resolve inside the week on screen (`week_start`, a Sunday) --
    the convention the board and the single-date reader already share --
    and, with no week on screen, to the next such day from today.
    """
    anchor = parse(today) or israel_today()
    week = week_of(parse(week_start)) if parse(week_start) else None
    found = set(_explicit(text, anchor))
    found |= set(_weekdays(text, anchor, week))
    for word, offset in _RELATIVE:
        if re.search(r"(?<![א-ת])[ול]?%s(?![א-ת])" % word, text):
            found.add(anchor + datetime.timedelta(days=offset))
    found |= set(_weeks(text, anchor, week))
    days = sorted(found)
    if days and (days[-1] - days[0]).days >= MAX_DAYS:
        return []
    return [day.isoformat() for day in days]


def weekdays_named(text: str) -> List[str]:
    """The weekday names a sentence uses, in week order, for a standing rule."""
    named = {match.group(1) for match in _WEEKDAY.finditer(text)}
    return [name for name in _WEEKDAY_NAMES if name in named]


def only_weekdays(text: str) -> bool:
    """Whether every date in the sentence came from a bare weekday name."""
    if _DATE_RE.search(text) or re.search(r"היום|מחר|השבוע|שבוע הבא", text):
        return False
    return bool(_WEEKDAY.search(text))


def _explicit(text: str, anchor: datetime.date) -> List[datetime.date]:
    days = []
    for match in _DATE_RANGE.finditer(text):
        first, last = _date(match.group(1), anchor), _date(match.group(2), anchor)
        if first and last and first <= last:
            days.extend(_span(first, last))
    for match in _DATE_RE.finditer(text):
        day = _date(match.group(1), anchor)
        if day:
            days.append(day)
    return days


def _weekdays(text, anchor, week) -> List[datetime.date]:
    days = []
    for match in _WEEKDAY_RANGE.finditer(text):
        first = _weekday(match.group(1), anchor, week)
        last = _weekday(match.group(2), anchor, week)
        if first and last:
            if last < first:
                last += datetime.timedelta(days=7)
            days.extend(_span(first, last))
    for match in _WEEKDAY.finditer(text):
        day = _weekday(match.group(1), anchor, week)
        if day:
            days.append(day)
    return days


def _weeks(text, anchor, week) -> List[datetime.date]:
    if re.search(r"שבוע הבא|בשבוע הבא", text):
        return week_of(anchor + datetime.timedelta(days=7))
    # "השבוע", never a bare "שבוע": "חולה כבר שבוע" is a duration, not dates.
    if re.search(r"(?<![א-ת])(?:ב|ו|ל)?(?:כל\s+)?השבוע(?![א-ת])", text) \
            and "שעבר" not in text:
        return week or week_of(anchor)
    return []


def _weekday(name: str, anchor: datetime.date, week) -> Optional[datetime.date]:
    index = _WEEKDAY_NAMES.index(name)
    if week:
        return week[index]
    ahead = (index - (anchor.weekday() + 1) % 7) % 7
    return anchor + datetime.timedelta(days=ahead)


def _date(value: str, anchor: datetime.date) -> Optional[datetime.date]:
    if "-" in value:
        return parse(value)
    parts = [int(part) for part in re.split(r"[/.]", value)]
    year = parts[2] if len(parts) > 2 else anchor.year
    year += 2000 if year < 100 else 0
    try:
        day = datetime.date(year, parts[1], parts[0])
    except ValueError:
        return None
    # "3.1" written in late December is next January, not last January.
    if len(parts) == 2 and (anchor - day).days > 60:
        day = day.replace(year=year + 1)
    return day


def _span(first: datetime.date, last: datetime.date) -> List[datetime.date]:
    if (last - first).days >= MAX_DAYS:
        return []
    return [first + datetime.timedelta(days=n) for n in range((last - first).days + 1)]
