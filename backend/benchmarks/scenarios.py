"""Synthetic teams the solver benchmark runs on, built the same every time.

Each scenario is a function returning a `Scenario`: a profile, the dates
to solve and the inputs a real build would hand the solver (absences, soft
absences, requests). Randomness is seeded per scenario, so two runs of the
benchmark measure the same problem and differ only in what the solver did.

The four shapes stand for what the product actually meets, smallest first:

| name | what it stresses |
|---|---|
| `small` | two shifts, eight people, two weeks: the floor |
| `nights` | a night shift, a required role, shift managers, wishes |
| `rotation` | weekend closures by group (סבב) and נחפפים beside trainers |
| `large` | forty people, four shifts, four weeks, many requests |

Names are synthetic (`עובד 07`), never real people.
"""

import datetime
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List

MORNING, EVENING, NIGHT, DUTY = "בוקר", "ערב", "לילה", "תורנות"
MEDIC, OFFICER = "חובש", "קצין"


@dataclass
class Scenario:
    name: str
    profile: dict
    starts_on: str
    ends_on: str
    availability: List[dict] = field(default_factory=list)
    requests: List[dict] = field(default_factory=list)


def _dates(starts_on: str, days: int) -> List[str]:
    first = datetime.date.fromisoformat(starts_on)
    return [(first + datetime.timedelta(days=step)).isoformat() for step in range(days)]


def _shift(name: str, start: str, end: str, headcount: int, roles=None,
           manager: bool = False, weekend: int = 0) -> dict:
    """A shift every day; `weekend` overrides the headcount Friday–Saturday."""
    staffing = [{"days": [], "headcount": headcount, "required_roles": list(roles or [])}]
    if weekend:
        staffing.append({"days": ["שישי", "שבת"], "headcount": weekend,
                         "required_roles": list(roles or [])})
    return {"name": name, "start_time": start, "end_time": end, "days": [],
            "requires_shift_manager": manager, "staffing": staffing}


def _people(count: int, rng: random.Random, medics: int = 0, managers: int = 0) -> List[dict]:
    people = []
    for number in range(1, count + 1):
        person = {"name": "עובד %02d" % number}
        if number <= medics:
            person["roles"] = [MEDIC]
        if medics < number <= medics + managers:
            person["is_shift_manager"] = True
        people.append(person)
    rng.shuffle(people)
    return people


def _absences(people: List[dict], dates: List[str], rng: random.Random,
              hard: int, soft: int) -> List[dict]:
    """`hard` blocked days and `soft` unwanted days, spread over the team."""
    rows = []
    for count, is_hard in ((hard, True), (soft, False)):
        for _ in range(count):
            person = rng.choice(people)["name"]
            rows.append({"employee": person, "date": rng.choice(dates), "available": False,
                         "is_hard": is_hard, "reason": "חופשה" if is_hard else "מעדיף/ה לא"})
    return rows


def _wishes(people: List[dict], dates: List[str], shifts: List[str],
            rng: random.Random, count: int) -> List[dict]:
    """Soft requests of the shapes the translator produces most."""
    requests = []
    for _ in range(count):
        person = rng.choice(people)["name"]
        shape = rng.random()
        if shape < 0.4:
            requests.append({"kind": "prefer", "employees": [person], "shifts": [rng.choice(shifts)],
                             "dates": [rng.choice(dates)], "reason": "ביקש/ה"})
        elif shape < 0.8:
            requests.append({"kind": "avoid", "employees": [person], "shifts": [rng.choice(shifts)],
                             "reason": "מעדיף/ה להימנע"})
        else:
            requests.append({"kind": "max_count", "employees": [person], "count": 4, "per": "week",
                             "reason": "עד ארבע בשבוע"})
    return requests


def small() -> Scenario:
    rng = random.Random(1)
    people = _people(8, rng)
    dates = _dates("2026-09-06", 14)
    profile = {"workplace": {"name": "בנצ'מרק"}, "employees": people,
               "shifts": [_shift(MORNING, "07:00", "15:00", 2), _shift(EVENING, "15:00", "23:00", 1)]}
    return Scenario("small", profile, dates[0], dates[-1],
                    availability=_absences(people, dates, rng, hard=4, soft=4))


def nights() -> Scenario:
    rng = random.Random(2)
    people = _people(18, rng, medics=5, managers=5)
    dates = _dates("2026-09-06", 28)
    shifts = [_shift(MORNING, "07:00", "15:00", 3, [MEDIC], manager=True, weekend=2),
              _shift(EVENING, "15:00", "23:00", 2, manager=True),
              _shift(NIGHT, "23:00", "07:00", 2)]
    profile = {"workplace": {"name": "בנצ'מרק"}, "employees": people, "shifts": shifts}
    return Scenario("nights", profile, dates[0], dates[-1],
                    availability=_absences(people, dates, rng, hard=20, soft=20),
                    requests=_wishes(people, dates, [MORNING, EVENING, NIGHT], rng, 15))


def rotation() -> Scenario:
    rng = random.Random(3)
    people = _people(20, rng, medics=4, managers=4)
    for position, person in enumerate(people):
        person.update(exit_pattern="round", rotation_group="אב"[position % 2])
    trainers = [person["name"] for person in people[:3]]
    for person in people[:3]:
        person["can_train"] = True
    people += [{"name": "נחפף %d" % number, "is_trainee": True, "counts_toward_staffing": False,
                "trainers": trainers} for number in (1, 2)]
    dates = _dates("2026-09-06", 28)
    shifts = [_shift(MORNING, "07:00", "15:00", 3, [MEDIC], manager=True, weekend=2),
              _shift(EVENING, "15:00", "23:00", 2, weekend=2),
              _shift(NIGHT, "23:00", "07:00", 1)]
    profile = {"workplace": {"name": "בנצ'מרק", "round_first_closure_date": "2026-09-12",
                             "round_first_closure_group": "א"},
               "employees": people, "shifts": shifts}
    return Scenario("rotation", profile, dates[0], dates[-1],
                    availability=_absences(people[:-2], dates, rng, hard=12, soft=12),
                    requests=_wishes(people[:-2], dates, [MORNING, EVENING, NIGHT], rng, 10))


def large() -> Scenario:
    rng = random.Random(4)
    people = _people(40, rng, medics=10, managers=8)
    dates = _dates("2026-09-06", 28)
    shifts = [_shift(MORNING, "07:00", "15:00", 5, [MEDIC], manager=True, weekend=3),
              _shift(EVENING, "15:00", "23:00", 4, [MEDIC], manager=True, weekend=3),
              _shift(NIGHT, "23:00", "07:00", 3),
              _shift(DUTY, "09:00", "21:00", 1)]
    profile = {"workplace": {"name": "בנצ'מרק"}, "employees": people, "shifts": shifts}
    return Scenario("large", profile, dates[0], dates[-1],
                    availability=_absences(people, dates, rng, hard=60, soft=50),
                    requests=_wishes(people, dates, [MORNING, EVENING, NIGHT, DUTY], rng, 40))


SCENARIOS: Dict[str, Callable[[], Scenario]] = {
    "small": small, "nights": nights, "rotation": rotation, "large": large,
}
