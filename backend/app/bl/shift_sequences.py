"""Compile standing sequence and rotation rules against the team's vocabulary."""

import datetime as dt
import re
from dataclasses import dataclass

from app.bl.rotation import day_cycles
from app.bl.shared import parse_date
from app.bl.audit.values import minutes

_DAY = dt.timedelta(days=1)
_RETURN_MORNING = {"אין לשבץ בוקר ביום החזרה לבסיס", "אין לשבץ משמרת בוקר ביום החזרה לבסיס",
                   "אין לשבץ בוקר ביום שבו עולים לבסיס"}
_UNAVAILABLE = "אין לשבץ משמרת בזמן אי-זמינות שחייל או קצין מגישים"
_ALIASES = {"בקר": "בוקר", "ערבים": "ערב", "לילות": "לילה", "בקרים": "בוקר"}


@dataclass(frozen=True)
class ShiftRule:
    kind: str
    shift: str
    text: str
    hard: bool
    previous: str = ""
    count: int = 0
    person: str = ""
    # "ערב אחרי לילה" also forbids the evening of the day after that night;
    # "מיד אחרי" means only the shift that directly follows.
    next_day: bool = False


def _sentence(row):
    if not isinstance(row, dict):
        return ""
    sentence = " ".join(str(row.get("text") or "").split()).rstrip(".").replace("־", "-")
    return re.sub(r"^(?:אסור לשבץ|לא לשבץ) ", "אין לשבץ ", sentence)


def compile_rule(row, profile):
    if not isinstance(row, dict):
        return None
    text = _sentence(row)
    hard = row.get("priority", "hard") == "hard"
    shifts = {s["name"]: s for s in profile.get("shifts") or [] if s.get("name")}

    def named(word):
        return word if word in shifts else _ALIASES.get(word, word)

    if text == _UNAVAILABLE and hard:
        return ShiftRule("availability", "", text, hard)
    run = re.fullmatch(r"אין לשבץ (שני|שתי|[2-9]) (.+?) (?:ב?רצף|רצוף)", text)
    if run and named(run[2]) in shifts:
        count = 2 if run[1] in ("שני", "שתי") else int(run[1])
        return ShiftRule("run", named(run[2]), text, hard, count=count)
    pair = re.fullmatch(r"אין לשבץ (.+?) (?:מיד )?אחרי (.+)", text)
    if pair and named(pair[1]) in shifts and named(pair[2]) in shifts:
        following, previous = named(pair[1]), named(pair[2])
        if all(minutes(shifts[name].get("start_time")) is not None for name in (following, previous)):
            later_on_the_clock = minutes(shifts[previous]["start_time"]) < minutes(shifts[following]["start_time"])
            return ShiftRule("after", following, text, hard, previous=previous,
                             next_day=later_on_the_clock and " מיד אחרי " not in text)
    leave = re.fullmatch(r"אין לשבץ (.+?) לפני יציאה הביתה", text)
    arrive = re.fullmatch(r"אין לשבץ (.+?) בבוקר שבו עולים לבסיס", text)
    general_return = text in _RETURN_MORNING
    if not leave and not arrive and not general_return:
        return None
    people = profile.get("employees") or []
    target = ""
    if general_return:
        shift = named("בוקר")
    elif arrive:
        if any(p.get("name") == arrive[1] for p in people):
            target, shift = arrive[1], named("בוקר")
        else:
            shift = named(arrive[1])
    else:
        shift = named(leave[1])
    if shift not in shifts or minutes(shifts[shift].get("start_time")) is None:
        return None
    if arrive and minutes(shifts[shift]["start_time"]) >= 12 * 60:
        return None
    applicable = [p for p in people if not target or p.get("name") == target]
    if not applicable or not all(day_cycles.day_cycle(profile, p.get("exit_pattern")) and
                                 p.get("rotation_group") for p in applicable):
        return None
    return ShiftRule("departure" if leave else "return", shift, text, hard, person=target)


def missing_return_subject(row, profile):
    text = _sentence(row)
    match = re.fullmatch(r"אין לשבץ (.+?) בבוקר שבו עולים לבסיס", text)
    if match:
        names = {item.get("name") for field in ("employees", "shifts")
                 for item in profile.get(field) or [] if isinstance(item, dict)}
        if match[1] not in names:
            return "למי או לאיזו משמרת מתייחס השם %s בבוקר החזרה לבסיס?" % match[1]
    return ""


def rules_for(profile):
    return [rule for row in profile.get("rules") or [] if (rule := compile_rule(row, profile))]


def forbidden_groups(rule, slots, profile, person):
    """Yield sets of (date, shift) that cannot all be assigned to one person."""
    if rule.kind == "availability" or (rule.person and person.get("name") != rule.person):
        return
    for (date, shift), slot in slots.items():
        if shift != rule.shift:
            continue
        day = parse_date(date)
        if day is None:
            continue
        if rule.kind == "run":
            group = [((day - n * _DAY).isoformat(), shift) for n in range(rule.count)]
        elif rule.kind == "after":
            today = (date, rule.previous)
            previous = slots.get(today) or next((s for s in profile["shifts"] if s["name"] == rule.previous), {})
            first, second = minutes(previous.get("start_time")), minutes(slot.get("start_time"))
            if first is None or second is None:
                continue
            prior = day if first < second else day - _DAY
            group = [(prior.isoformat(), rule.previous), (date, shift)]
            if rule.next_day:
                yesterday = [((day - _DAY).isoformat(), rule.previous), (date, shift)]
                if all(key in slots for key in yesterday):
                    yield yesterday
        else:
            cycle = day_cycles.day_cycle(profile, person.get("exit_pattern"))
            when = minutes(slot.get("start_time"))
            if cycle is None or when is None:
                continue
            begins = dt.datetime.combine(day, dt.time()) + dt.timedelta(minutes=when)
            windows = day_cycles.home_windows(cycle, person["rotation_group"], day - _DAY, day + _DAY)
            if rule.kind == "departure":
                blocked = any(begins < leave <= begins + _DAY for leave, _ in windows)
            else:
                blocked = any(back.date() == day for _, back in windows)
            if not blocked:
                continue
            group = [(date, shift)]
        if all(key in slots for key in group):
            yield group
