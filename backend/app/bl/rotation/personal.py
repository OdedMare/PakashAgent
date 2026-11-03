"""Patterns one person carries alone: none, daily, and one weekend in N.

The lettered cycles and the day cycles turn a *group*; these three describe
one soldier and need no anchor shared with anybody.

- `none` — no exits at all: a civilian, a career soldier, anybody the
  rotation does not speak for. Nothing is blocked and nothing is claimed.
  Saying it is what separates "no rotation" from "forgot to set one".
- `daily` — goes home every day. `daily_days` are the days they come (empty
  is every day) and `daily_start`–`daily_end` the hours they are on base
  (blank is the whole day). A slot outside those hours, or on a day they do
  not come, is refused.
- `personal` — closes one weekend in `closure_every` (2–8), starting with
  the weekend of `closure_from`; home on every other weekend, from Thursday
  to the Sunday handover, like an ungrouped חמשושים soldier. One commander
  on 1ל5 is this, not a חמישון with four empty groups.
"""

import datetime
from typing import List, Optional

from app.bl.rotation.vocabulary import minutes, parse_date, saturday_of, text
from app.bl.shared import hebrew_weekday, weekday_key

PERSONAL_PATTERNS = frozenset({"none", "daily", "personal"})
EVERY_RANGE = (2, 8)

_DAY = datetime.timedelta(days=1)
_WEEK = datetime.timedelta(days=7)


def is_personal(pattern: str) -> bool:
    return text(pattern) in PERSONAL_PATTERNS


def every(person: dict) -> Optional[int]:
    try:
        value = int(person.get("closure_every") or 0)
    except (TypeError, ValueError):
        return None
    return value if EVERY_RANGE[0] <= value <= EVERY_RANGE[1] else None


def first_saturday(person: dict) -> Optional[datetime.date]:
    day = parse_date(person.get("closure_from"))
    return saturday_of(day) if day else None


def closes_on(person: dict, saturday: datetime.date) -> bool:
    """Whether a `personal` soldier holds the weekend ending `saturday`."""
    count, anchor = every(person), first_saturday(person)
    if count is None or anchor is None:
        return False
    return ((saturday - anchor).days // 7) % count == 0


def closure_days(person: dict, start: datetime.date, end: datetime.date,
                 handover: List[str], lead: int) -> List[dict]:
    """A `personal` soldier's own weekends, shaped like a cycle's rows."""
    if every(person) is None or first_saturday(person) is None:
        return []
    rows = []
    saturday = saturday_of(start) - _WEEK
    while saturday - 6 * _DAY <= end:
        if closes_on(person, saturday):
            day = saturday - lead * _DAY
            last = saturday + (_DAY if handover else datetime.timedelta(0))
            while day <= last:
                if start <= day <= end:
                    rows.append(dict(date=day.isoformat(), weekend=saturday.isoformat(),
                                     group="", pattern="personal", cycle="",
                                     is_saturday=day == saturday, until_handover=day > saturday,
                                     shifts=list(handover) if day > saturday else []))
                day += _DAY
        saturday += _WEEK
    return rows


def status(pattern: str, person: dict, slot: dict, handover: List[str],
           lead: int) -> Optional[bool]:
    """None when the pattern says nothing; False when it refuses the slot."""
    day = parse_date(slot.get("slot_date"))
    if day is None or pattern == "none":
        return None
    if pattern == "daily":
        return _daily(person, day, slot)
    if pattern == "personal":
        return _weekend_home(person, day, slot["shift_name"], handover, lead)
    return None


def _daily(person: dict, day: datetime.date, slot: dict) -> Optional[bool]:
    days = {weekday_key(item) for item in person.get("daily_days") or []}
    if days and weekday_key(hebrew_weekday(day)) not in days:
        return False
    opens, closes = minutes(person.get("daily_start")), minutes(person.get("daily_end"))
    if opens is None and closes is None:
        return None
    begins, ends = minutes(slot.get("start_time")), minutes(slot.get("end_time"))
    if begins is None or ends is None:
        return None  # no clock to compare against: the day decides
    opens = 0 if opens is None else opens
    closes = 1440 if closes is None or closes == 0 else closes
    if ends <= begins:
        ends += 1440  # an overnight shift runs past midnight
    if closes <= opens:
        closes += 1440
    return None if opens <= begins and ends <= closes else False


def _weekend_home(person: dict, day: datetime.date, shift: str,
                  handover: List[str], lead: int) -> Optional[bool]:
    """Home from Thursday to the Sunday handover on every weekend not theirs."""
    if every(person) is None or first_saturday(person) is None:
        return None
    # The Sunday after a weekend belongs to the weekend before it.
    saturday = saturday_of(day - _DAY) if day.weekday() == 6 else saturday_of(day)
    if (saturday - day).days > lead or (day > saturday and shift not in handover):
        return None
    return None if closes_on(person, saturday) else False


def configuration_errors(person: dict) -> List[str]:
    name = text(person.get("name")) or "איש הצוות"
    if text(person.get("exit_pattern")) != "personal":
        return []
    errors = []
    if every(person) is None:
        errors.append("לא הוגדר כל כמה שבתות %s סוגר/ת (2 עד 8)" % name)
    if first_saturday(person) is None:
        errors.append("לא הוגדר תאריך הסגירה הראשונה של %s" % name)
    return errors
