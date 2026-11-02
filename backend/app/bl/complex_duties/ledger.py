"""What the duty fill and the balance read, gathered across a מכלול once.

Every soldier of every active משמרת, the מכלול's duties, each soldier's
shift dates, and what rules a soldier out of a whole day: leaving, a hard
whole-day constraint or a team's own duty, or being home on the cycle --
read through the same `bl/rotation` gates the solver uses, so a soldier
the fill proposes is one the משמרת's own board would have on base.
"""

import datetime
from typing import Dict, List, Set, Tuple

from app.bl.complex_duties.fill import WINDOW_DAYS
from app.bl.rotation.presence import closure_status, presence_status
from app.bl.shared import text

Key = Tuple[str, str]


class DutyLedger:
    def __init__(self, repository, complexes, complex_id: str,
                 first: datetime.date, last: datetime.date, window_days: int = WINDOW_DAYS):
        self.first, self.last = first, last
        self.since = first - datetime.timedelta(days=window_days)
        self.soldiers: List[dict] = []
        self.shift_days: Dict[Key, Set[datetime.date]] = {}
        self._blocked: Set[tuple] = set()
        for team in complexes.describe(complex_id)["teams"]:
            if team["active"]:
                self._read_team(repository, team)
        self.duties = repository.complex_duties(
            complex_id, self.since.isoformat(), last.isoformat())

    def _read_team(self, repository, team: dict) -> None:
        profile = repository.team_profile(team["id"]) or {}
        for person in profile.get("employees") or []:
            if isinstance(person, dict) and text(person.get("name")):
                self.soldiers.append({
                    "team_id": team["id"], "team_name": team["name"],
                    "name": text(person["name"]), "role": text(person.get("role")),
                    "person": person, "profile": profile,
                })
        for row in repository.team_shift_rows(
                team["id"], self.since.isoformat(), self.last.isoformat()):
            day = _day(row["slot_date"])
            if day is not None:
                self.shift_days.setdefault((team["id"], row["employee"]), set()).add(day)
        for row in repository.availability(
                team["id"], self.first.isoformat(), self.last.isoformat()):
            if _blocks_day(row):
                day = _day(row.get("constraint_date"))
                if day is not None:
                    self._blocked.add((team["id"], row["employee"], day))

    def ruled_out(self, soldier: dict, day: datetime.date) -> str:
        """Why this soldier cannot stand a whole-day duty on `day`, or ''."""
        leaves = _day(soldier["person"].get("inactive_from"))
        if leaves is not None and leaves <= day:
            return "סיים/ה את השירות"
        if (soldier["team_id"], soldier["name"], day) in self._blocked:
            return "אילוץ ליום הזה"
        if _home(soldier, day):
            return "בבית לפי הסבב"
        return ""

    def serving(self, soldier: dict) -> bool:
        leaves = _day(soldier["person"].get("inactive_from"))
        return leaves is None or leaves > self.first


def _blocks_day(row: dict) -> bool:
    """A hard row that takes the whole day: an unavailability with no shift
    and no hours, or a team's own operational duty (a מכלול duty is counted
    from the duties themselves)."""
    if text(row.get("source")) == "complex" or row.get("is_hard") is False:
        return False
    if text(row.get("constraint_type")) == "duty":
        return True
    return not row.get("available") and not text(row.get("shift_name")) \
        and not text(row.get("start_time")) and not text(row.get("end_time"))


def _home(soldier: dict, day: datetime.date) -> bool:
    """Home on the cycle for any part of the day: a duty holds all of it."""
    slot = {"slot_date": day.isoformat(), "shift_name": "",
            "start_time": "00:00", "end_time": "00:00"}
    try:
        status = presence_status(soldier["profile"], soldier["person"], slot)
        if status is None:
            status = closure_status(soldier["profile"], soldier["person"], slot)
    except (KeyError, TypeError, ValueError):
        return False
    return status is False


def _day(value):
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None
