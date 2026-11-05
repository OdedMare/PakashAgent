"""The fairest soldier for every open duty seat: a proposal, never a write.

Pure arithmetic over what `ledger.py` gathered, no model and no repository
(the same shape as `bl/simulate/`): the commander sees every pick with its
reason and approves it, or not (D20).

Greedy, a day at a time and a kind of duty at a time, updating the counts
as it goes -- so the third seat of a week sees the first two. A soldier is
**ruled out** when they are home on the cycle, hold a hard whole-day
constraint, already stand a duty that day, or have left. Among the rest
the order is, first deciding:

1. **not within `MIN_GAP_DAYS` of another duty of theirs**, before or
   after (a stored future one counts too). Duties are spread wide, never
   day after day: someone that close is picked only when nobody else is
   free, and then whoever is furthest;
2. the fewest weighted duty days over the window (8 weeks back to the span's end);
3. on a Friday or Saturday, the fewest weekend duties;
4. the widest gap to their nearest duty -- among equals, the soldier whose
   duties lie furthest from this day, so the spread stays large;
5. no shift of their own the duty would take -- that day's, or a night
   from the evening before (`busy_days`): every one is a seat vacated and
   rebuilt in a משמרת, so a free soldier wins among equals;
6. the lightest whole load -- duties plus shifts;
7. the משמרת and the name, so the same input gives the same answer.
"""

import datetime
from typing import Callable, Dict, List, Tuple

from app.bl.complex_duties.values import runs_on

Key = Tuple[str, str]  # (team_id, soldier name)

# Friday and Saturday by `date.weekday()`.
_WEEKEND = (4, 5)
# How far back the counts reach.
WINDOW_DAYS = 56
# The fewest days between two duties of one soldier the fill proposes while
# anybody else is free: six apart leaves at least five days clear between.
MIN_GAP_DAYS = 6
# No duty at all reads as this far apart.
_FAR = 10 ** 6


def suggest(
    types: List[dict],
    dates: List[datetime.date],
    soldiers: List[dict],
    duties: List[dict],
    shift_days: Dict[Key, set],
    ruled_out: Callable[[dict, datetime.date], str],
    busy_days: Dict[Key, set] = None,
) -> dict:
    """`soldiers` carry `team_id`, `team_name` and `name`; `duties` are the
    מכלול's stored rows over the window (blocking or recorded); `shift_days`
    is each soldier's dates with a shift; `ruled_out(soldier, day)` names why
    a soldier cannot stand a duty that day, or is empty. `busy_days` are
    the days a duty would take a shift from (default: the shift dates)."""
    state = _State(soldiers, duties, shift_days, busy_days)
    proposals, unfilled = [], []
    for day in dates:
        for duty_type in types:
            if not duty_type.get("active", True) or not runs_on(duty_type, day):
                continue
            open_seats = duty_type["seats"] - state.seated(duty_type["id"], day)
            for _ in range(max(0, open_seats)):
                pick = state.best(day, ruled_out)
                if pick is None:
                    unfilled.append({"duty_type_id": duty_type["id"],
                                     "duty_type": duty_type["name"],
                                     "duty_date": day.isoformat()})
                    continue
                proposals.append(dict(
                    duty_type_id=duty_type["id"], duty_type=duty_type["name"],
                    team_id=pick["team_id"], team_name=pick["team_name"],
                    employee=pick["name"], duty_date=day.isoformat(),
                    reason=state.reason(pick, day),
                ))
                state.add(pick, duty_type, day)
    return {"proposals": proposals, "unfilled": unfilled}


class _State:
    def __init__(self, soldiers, duties, shift_days, busy_days=None):
        self.soldiers = soldiers
        self.shift_days = shift_days
        self.busy_days = busy_days if busy_days is not None else shift_days
        self.load: Dict[Key, int] = {}
        self.weekend: Dict[Key, int] = {}
        self.dates: Dict[Key, List[datetime.date]] = {}
        self.on_duty: set = set()          # (key, date)
        self.by_type: Dict[tuple, int] = {}  # (type_id, date) -> blocking seats
        for row in duties:
            day = _day(row.get("duty_date"))
            if day is None:
                continue
            self._count(_key(row["team_id"], row["employee"]), _weight(row), day)
            if row.get("blocks", True):
                slot = (row["duty_type_id"], day)
                self.by_type[slot] = self.by_type.get(slot, 0) + 1

    def _count(self, key: Key, weight: int, day: datetime.date) -> None:
        self.load[key] = self.load.get(key, 0) + weight
        self.weekend[key] = self.weekend.get(key, 0) + (day.weekday() in _WEEKEND)
        self.dates.setdefault(key, []).append(day)
        self.on_duty.add((key, day))

    def gap(self, key: Key, day: datetime.date) -> int:
        """Days from `day` to this soldier's nearest duty, either side."""
        return min((abs((day - other).days) for other in self.dates.get(key, ())),
                   default=_FAR)

    def seated(self, type_id: str, day: datetime.date) -> int:
        return self.by_type.get((type_id, day), 0)

    def best(self, day, ruled_out):
        free = [soldier for soldier in self.soldiers
                if (_of(soldier), day) not in self.on_duty and not ruled_out(soldier, day)]
        if not free:
            return None
        weekend = day.weekday() in _WEEKEND
        return min(free, key=lambda soldier: self._rank(soldier, day, weekend))

    def _rank(self, soldier, day, weekend):
        key = _of(soldier)
        shifts = len(self.shift_days.get(key, ()))
        gap = self.gap(key, day)
        close = gap < MIN_GAP_DAYS
        return (
            close,
            -gap if close else 0,
            self.load.get(key, 0),
            self.weekend.get(key, 0) if weekend else 0,
            -gap,
            day in self.busy_days.get(key, ()),
            self.load.get(key, 0) + shifts,
            soldier["team_name"], soldier["name"],
        )

    def reason(self, soldier, day) -> str:
        key = _of(soldier)
        load, shifts = self.load.get(key, 0), len(self.shift_days.get(key, ()))
        parts = ["%d ימי תורנות ב־8 השבועות האחרונים" % load if load else "בלי תורנויות ב־8 השבועות האחרונים",
                 "%d משמרות" % shifts]
        if day.weekday() in _WEEKEND:
            parts.append("%d תורנויות סופ״ש" % self.weekend.get(key, 0))
        gap = self.gap(key, day)
        if gap < _FAR:
            parts.append("התורנות הקרובה שלו/ה במרחק %d ימים" % gap)
        if gap < MIN_GAP_DAYS:
            parts.append("שים לב: קרוב לתורנות אחרת — לא נמצא חייל פנוי רחוק יותר")
        if day in self.busy_days.get(key, ()):
            parts.append("שים לב: משובץ/ת למשמרת שהתורנות תחסום — היא תפונה ותושלם מחדש")
        return ", ".join(parts)

    def add(self, soldier, duty_type, day) -> None:
        self._count(_of(soldier), _weight(duty_type), day)
        slot = (duty_type["id"], day)
        self.by_type[slot] = self.by_type.get(slot, 0) + 1


def _of(soldier: dict) -> Key:
    return _key(soldier["team_id"], soldier["name"])


def _key(team_id, name) -> Key:
    return (str(team_id), str(name))


def _weight(row: dict) -> int:
    weight = row.get("weight", 1)
    return max(0, weight) if isinstance(weight, int) and not isinstance(weight, bool) else 1


def _day(value):
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None
