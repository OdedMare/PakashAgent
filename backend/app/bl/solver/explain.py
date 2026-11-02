"""Why a seat stayed empty: who on the roster could not take it, and why.

"לא נמצא שיבוץ חוקי" alone reads as the solver failing; nearly always the
team simply had nobody left for that slot. So every seat, required role
and shift-manager seat the answer leaves open gets a note that counts the
roster against it, from the same tests the solver ran:

- `problem.refusal` for what made a placement illegal before any variable
  existed — not qualified, home on the rotation, on a duty, no longer
  serving, another hard availability, a hard `avoid`;
- the finished schedule for what the rules then ruled out — already on an
  overlapping shift, too little rest beside another shift, a run of days
  or the weekly hours it would break;
- a hard request naming the person (`max_count`, `not_together`, ...) when
  none of those applies, and otherwise "free": somebody who could have
  stood there and was not placed, which points at the time limit.

Counted from the answer, after solving, so it costs the solve nothing. Names
are listed for a reason only a few people share.
"""

import datetime
from typing import Dict, List, Optional

from app.bl.audit import counts_toward_staffing
from app.bl.audit.roster import iso_week
from app.bl.audit.values import number
from app.bl.schedule_requests import covers
from app.bl.solver.competence import reserve_days, week_of
from app.bl.solver.rows import roles

LABELS = {
    "ineligible": "לא כשירים למשמרת",
    "unavailable": "לא זמינים (אילוץ או היעדרות)",
    "away": "בבית לפי הסבב",
    "duty": "בתורנות או במשימה",
    "retired": "סיימו את עבודתם",
    "avoid": "ביקשו באופן מחייב לא לעבוד בה",
    "busy": "משובצים במשמרת חופפת",
    "rest": "בלי מנוחה מספקת ממשמרת סמוכה",
    "consecutive": "יחרגו מרצף הימים המותר",
    "hours": "יחרגו משעות העבודה השבועיות",
    "reserve": "מיצו את ימי המילואים בשבוע",
    "request": "מוגבלים בבקשה מחייבת אחרת",
    "free": "פנויים ולא שובצו (ייתכן שזמן הפתרון לא הספיק)",
}
# Requests that can rule out one more shift without forbidding this one.
_BOUNDING = ("max_count", "not_together", "min_rest", "max_consecutive", "requires_with")
# A reason this few people share lists them by name.
_NAMED = 3


def coverage_notes(problem, chosen: List[dict]) -> List[str]:
    """One note per seat, role or shift manager the answer leaves open."""
    board = _Board(problem, chosen)
    notes = []
    for index, slot in enumerate(problem.slots):
        on = board.on_slot(index)
        counted = [name for name in on if name in problem.staff]
        short = int(slot.get("headcount") or 0) - len(counted)
        where = "%s בתאריך %s" % (slot["shift_name"], slot["slot_date"])
        if short > 0:
            notes.append("לא נמצא שיבוץ חוקי ל%s; המשמרת נשארה בחוסר של %d. %s" % (
                where, short, board.why(index, list(problem.staff))))
        present = set().union(*(roles(problem.people[name]) for name in counted)) if counted else set()
        for role in slot.get("required_roles") or []:
            if role not in present:
                notes.append(_missing("חסר/ה %s ב%s." % (role, where), board, index,
                                      lambda person, r=role: r in roles(person),
                                      "אין בצוות אף אחד/ת בתפקיד %s." % role))
        if slot.get("requires_shift_manager") and \
                not any(problem.people[name].get("is_shift_manager") for name in counted):
            notes.append(_missing("אין מפקד/ת משמרת ב%s." % where, board, index,
                                  lambda person: bool(person.get("is_shift_manager")),
                                  "אין בצוות אף אחד/ת שמוגדר/ת מפקד/ת משמרת."))
    return notes


def _missing(head: str, board, index: int, test, nobody: str) -> str:
    holders = [name for name in board.problem.staff if test(board.problem.people[name])]
    return "%s %s" % (head, board.why(index, holders) if holders else nobody)


class _Board:
    """The finished schedule per person, with the times the rules read."""

    def __init__(self, problem, chosen: List[dict]):
        self.problem = problem
        self.policy = problem.policy
        self.rows: Dict[str, List[dict]] = {}
        seen = set()
        for row in problem.fixed:
            self._add(row["employee"], row, seen)
        for row in chosen:
            index = problem.keys[(row["shift"], row["date"])]
            self._add(row["employee"], dict(problem.times[index], shift=row["shift"],
                                            date=row["date"]), seen)

    def _add(self, name: str, row: dict, seen: set) -> None:
        key = (name, row["shift"], row["date"])
        if key not in seen:
            seen.add(key)
            self.rows.setdefault(name, []).append(row)

    def on_slot(self, index: int) -> List[str]:
        slot = self.problem.slots[index]
        return [name for name, rows in self.rows.items()
                if any(row["shift"] == slot["shift_name"] and row["date"] == slot["slot_date"]
                       for row in rows)]

    def why(self, index: int, names: List[str]) -> str:
        """"מתוך N: 6 בבית לפי הסבב, 2 בלי מנוחה (אבי, בני)" over `names`
        who are not on the slot."""
        on = set(self.on_slot(index))
        groups: Dict[str, List[str]] = {}
        for name in names:
            if name not in on:
                groups.setdefault(self.reason(name, index), []).append(name)
        if not groups:
            return ""
        parts = []
        for reason, people in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
            named = " (%s)" % ", ".join(people) if len(people) <= _NAMED else ""
            parts.append("%d %s%s" % (len(people), LABELS[reason], named))
        return "מתוך %d: %s." % (len(names), ", ".join(parts))

    def reason(self, name: str, index: int) -> str:
        refused = self.problem.refusal(name, index)
        if refused:
            return refused
        slot, times = self.problem.slots[index], self.problem.times[index]
        rows = self.rows.get(name, [])
        clash = _clash(rows, slot, times, self.policy["min_rest_hours"])
        if clash:
            return clash
        if self._run(rows, slot["slot_date"]) > self.policy["max_consecutive_days"] > 0:
            return "consecutive"
        if self._hours(name, rows, slot, times):
            return "hours"
        if _reserve_spent(self.problem.people[name], rows, slot["slot_date"]):
            return "reserve"
        if any(request["is_hard"] and request["kind"] in _BOUNDING
               and name in request["employees"] + request["partners"]
               and covers(request, slot["shift_name"], slot["slot_date"])
               for request in self.problem.requests):
            return "request"
        return "free"

    def _run(self, rows: List[dict], day: str) -> int:
        """The run of worked days this date would join, counting itself."""
        worked = {row["date"] for row in rows} | {day}
        current = datetime.date.fromisoformat(day)
        length = 1
        for step in (-1, 1):
            probe = current + datetime.timedelta(days=step)
            while probe.isoformat() in worked:
                length += 1
                probe += datetime.timedelta(days=step)
        return length

    def _hours(self, name: str, rows: List[dict], slot: dict, times: dict) -> bool:
        limit = number(self.problem.people[name].get("max_weekly_hours"), 0.0) \
            or self.policy["max_weekly_hours"]
        week = iso_week(datetime.date.fromisoformat(slot["slot_date"]))
        carried = sum(row["hours"] or 0.0 for row in rows
                      if iso_week(datetime.date.fromisoformat(row["date"])) == week)
        return carried + (times["hours"] or 0.0) > limit + 1e-6


def _reserve_spent(person: dict, rows: List[dict], day: str) -> bool:
    """A reservist whose week already holds their stated days, this one not
    among them."""
    cap = reserve_days(person)
    if cap is None:
        return False
    worked = {row["date"] for row in rows if week_of(row["date"]) == week_of(day)}
    return day not in worked and len(worked) >= cap


def _clash(rows: List[dict], slot: dict, times: dict, minimum: float) -> Optional[str]:
    """`busy` beside an overlapping shift (or, with no clock, one the same
    day), `rest` beside one closer than the minimum rest."""
    begins, ends = times["begins"], times["ends"]
    for row in rows:
        if begins is None or row["begins"] is None:
            if row["date"] == slot["slot_date"]:
                return "busy"
            continue
        if row["begins"] < ends and begins < row["ends"]:
            return "busy"
        gap = (begins - row["ends"]) if row["ends"] <= begins else (row["begins"] - ends)
        if gap.total_seconds() / 3600.0 < minimum:
            return "rest"
    return None
