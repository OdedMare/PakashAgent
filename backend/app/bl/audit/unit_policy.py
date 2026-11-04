"""A unit's staffing standard: role counts, fallback roles, a cap on the weak,
qualifications and weekly shift limits.

Read by the solver (which states them as constraints and prices) and by
the audit (which reports a schedule that drifted from them), so both use
one arithmetic. Every value is optional; a profile with no `unit_policy`
block and no rated, qualified people behaves exactly as before.

Profile shape::

    shift: {"min_competence": "high"}         # a strong shift: medium/high/excellent

    unit_policy: {
        "max_weak_per_shift": 1,              # competence "weak" per shift; None = no cap
        "qualification_validity_days": 90,
        "role_fallbacks": {"קב\"ר גיאוגרפי": ["קב\"ר מודיעיני"]},
        "weekly_shifts": {"min": 2, "max": 4},          # service_type "reserve"
        "weekly_shifts_officers": {"min": 3, "max": 5},
        "weekly_shifts_ncos": {"min": 3, "max": 5},
        "weekly_shifts_regular": {"min": 3, "max": 5},  # legacy/default regular staff
    }

    employee: {"competence": "weak"|..., "service_type": "reserve"|...,
               "qualifications": [{"role": "אלחוט", "last_active": "2026-09-01"}],
               "min_weekly_shifts": 2, "max_weekly_shifts": 4}  # over the team's

`competence` and `service_type` are the roster's own fields (the solver's
competence balance and reservist days read them too, `solver/competence.py`);
this module only adds a cap on the weak and team-wide weekly limits beside
the days a week a reservist, or a standard officer or NCO, comes
(`reserve_days_per_week`).
"""

import datetime
from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.bl.shared import number, parse_date, person_roles, text

DEFAULT_VALIDITY_DAYS = 90


def unit_policy(profile: Optional[dict]) -> dict:
    stated = (profile or {}).get("unit_policy")
    return stated if isinstance(stated, dict) else {}


def max_weak(profile: Optional[dict]) -> Optional[int]:
    value = unit_policy(profile).get("max_weak_per_shift")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, int(value))


def validity_days(profile: Optional[dict]) -> int:
    return int(number(unit_policy(profile).get("qualification_validity_days"),
                      DEFAULT_VALIDITY_DAYS)) or DEFAULT_VALIDITY_DAYS


def fallbacks(profile: Optional[dict]) -> Dict[str, List[str]]:
    """role -> the roles whose holders may fill it as second priority."""
    stated = unit_policy(profile).get("role_fallbacks")
    if not isinstance(stated, dict):
        return {}
    result = {}
    for role, others in stated.items():
        listed = [text(item) for item in others if text(item) and text(item) != text(role)] \
            if isinstance(others, list) else []
        if text(role) and listed:
            result[text(role)] = listed
    return result


def is_weak(person: Optional[dict]) -> bool:
    return text((person or {}).get("competence")) == "weak"


# A shift can ask for strong soldiers: `min_competence` on its definition
# names the lowest רמה מקצועית that belongs there.
LEVEL_ORDER = ("weak", "medium", "high", "excellent")


def required_level(shift: Optional[dict]) -> str:
    """The lowest level this shift asks for, or "" when it asks for none."""
    level = text((shift or {}).get("min_competence"))
    return level if level in LEVEL_ORDER[1:] else ""


def below_level(person: Optional[dict], shift: Optional[dict]) -> Optional[Tuple[str, str]]:
    """(their level, the shift's) when a rated person is below what the shift
    asks for. An unrated person is never below: the rating is optional, and
    an unknown is not a weak (the solver counts them as the team's mean)."""
    need = required_level(shift)
    have = text((person or {}).get("competence"))
    if not need or have not in LEVEL_ORDER:
        return None
    return (have, need) if LEVEL_ORDER.index(have) < LEVEL_ORDER.index(need) else None


def is_reservist(person: Optional[dict]) -> bool:
    return text((person or {}).get("service_type")) == "reserve"


# Standard-service ranks that come a set number of days a week, as a
# reservist does: an officer or an NCO who is on base, say, five days.
DAYS_A_WEEK_RANKS = ("officer", "nco")


def comes_days_a_week(person: Optional[dict]) -> bool:
    """A reservist, or a standard-service officer or NCO: the people whose
    `reserve_days_per_week` / `reserve_min_days` / `reserve_consecutive`
    shape their week. The field names say reserve because reservists had
    them first; the arithmetic is the same for both."""
    person = person or {}
    if is_reservist(person):
        return True
    return text(person.get("service_type") or "standard") == "standard" \
        and text(person.get("rank_group")) in DAYS_A_WEEK_RANKS


def reserve_days(person: Optional[dict]) -> Optional[int]:
    """The days a week this person comes (`reserve_days_per_week`, 1–7) —
    a reservist, or a standard officer or NCO — or None when nothing caps
    them. The solver's hard cap and the audit's warning both read it here,
    so a week the solver would refuse is one the audit reports when it got
    there another way (a pin, a hand placement, a cover chosen in the chat)."""
    if not comes_days_a_week(person):
        return None
    try:
        days = int((person or {}).get("reserve_days_per_week") or 0)
    except (TypeError, ValueError):
        return None
    return days if 1 <= days <= 7 else None


def reserve_limit_reached(person: Optional[dict], worked: Iterable, day) -> bool:
    """Whether adding `day` would exceed the reservist's cap in any
    seven-consecutive-day window containing it."""
    cap, target = reserve_days(person), _reserve_date(day)
    if cap is None or target is None:
        return False
    dates = {parsed for parsed in (_reserve_date(value) for value in worked) if parsed is not None}
    if target in dates:
        return False
    for offset in range(7):
        start = target - datetime.timedelta(days=offset)
        end = start + datetime.timedelta(days=6)
        if sum(start <= worked_day <= end for worked_day in dates) >= cap:
            return True
    return False


def reserve_excesses(person: Optional[dict], worked: Iterable) -> List[Tuple[datetime.date, datetime.date, int]]:
    """(offending day, window start, worked days) for each day beyond the
    cap, choosing the later assignments as the ones to move."""
    cap = reserve_days(person)
    if cap is None:
        return []
    dates = sorted({parsed for parsed in (_reserve_date(value) for value in worked) if parsed is not None})
    seen, excesses = [], []
    for day in dates:
        recent = [earlier for earlier in seen if (day - earlier).days <= 6]
        if len(recent) >= cap:
            excesses.append((day, day - datetime.timedelta(days=6), len(recent) + 1))
        seen.append(day)
    return excesses


def _reserve_date(value) -> Optional[datetime.date]:
    return value if isinstance(value, datetime.date) else parse_date(value)


def weekly_limits(profile: Optional[dict], person: Optional[dict]) -> Tuple[int, Optional[int]]:
    """(min, max) shifts per week for this person; max None means no cap.

    The soldier's own `min_weekly_shifts` / `max_weekly_shifts` win, each
    on its own; what they leave blank comes from their service type."""
    low, high = _team_limits(profile, person)
    own_low, own_high = (_whole((person or {}).get(key))
                         for key in ("min_weekly_shifts", "max_weekly_shifts"))
    return (low if own_low is None else own_low), (high if own_high is None else own_high)


def _whole(value) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, int(value))


def _team_limits(profile: Optional[dict], person: Optional[dict]) -> Tuple[int, Optional[int]]:
    policy = unit_policy(profile)
    rank = text((person or {}).get("rank_group"))
    key = "weekly_shifts" if is_reservist(person) else {
        "officer": "weekly_shifts_officers",
        "nco": "weekly_shifts_ncos",
    }.get(rank, "weekly_shifts_regular")
    block = policy.get(key)
    if key not in ("weekly_shifts", "weekly_shifts_regular"):
        regular = policy.get("weekly_shifts_regular")
        block = dict(regular) if isinstance(regular, dict) else {}
        if isinstance(policy.get(key), dict):
            block.update(policy[key])
    if not isinstance(block, dict) or not block:
        block = policy.get("weekly_shifts")
    if not isinstance(block, dict):
        return 0, None
    low = int(number(block.get("min"), 0))
    high = block.get("max")
    high = int(high) if isinstance(high, (int, float)) and not isinstance(high, bool) else None
    return max(0, low), (max(0, high) if high is not None else None)


def weekly_overflow(profile: Optional[dict]) -> int:
    """Shifts a week a person may take past their weekly `max`
    (`weekly_shifts_overflow`, 0 unless set): each one only when a seat
    would otherwise stay empty, and each one warned on."""
    value = unit_policy(profile).get("weekly_shifts_overflow")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def held_roles(person: Optional[dict]) -> Set[str]:
    """Every role a person may fill first-hand: `role`, `roles`, qualifications."""
    return person_roles(person or {})


def unit_week(day: datetime.date) -> datetime.date:
    """The Sunday a unit's week starts on (Sunday to Saturday, as the
    unit plans it; ISO weeks start on Monday and would split a weekend)."""
    return day - datetime.timedelta(days=(day.weekday() + 1) % 7)


def qualification_expired(profile: Optional[dict], person: Optional[dict], role: str,
                          on: datetime.date, worked: Optional[datetime.date] = None) -> bool:
    """True when every qualification this person has for `role` is stale.

    A role with no qualification row never expires: the unit did not ask
    to track it. A qualification with no last-active date is stale, as in
    the unit's own sheet. `worked`, the person's last shift before `on`,
    keeps every qualification alive like a typed date does.
    """
    rows = [row for row in (person or {}).get("qualifications") or []
            if isinstance(row, dict) and text(row.get("role")) == role]
    if not rows:
        return False
    limit = validity_days(profile)
    if worked is not None and worked <= on and (on - worked).days <= limit:
        return False
    for row in rows:
        try:
            last = datetime.date.fromisoformat(text(row.get("last_active")))
        except ValueError:
            continue
        if (on - last).days <= limit:
            return False
    return True


def role_needs(required: Sequence[str]) -> Counter:
    """`required_roles` as counts: a role listed three times needs three."""
    return Counter(text(role) for role in required or [] if text(role))


def cover(people_roles: List[Set[str]], needs: Counter,
          fallback: Dict[str, List[str]]) -> Tuple[Counter, int]:
    """Seat the people on the role seats, one seat each.

    Returns (missing seats per role, seats filled by a fallback holder).
    A maximum matching on first-hand holders first, then extended through
    fallback holders, so a fallback never displaces a first-hand fit.
    """
    seats = [role for role, count in sorted(needs.items()) for _ in range(count)]

    def edges(person: int, allow_fallback: bool) -> List[int]:
        held = people_roles[person]
        return [seat for seat, role in enumerate(seats)
                if role in held or (allow_fallback and held.intersection(fallback.get(role, ())))]

    owner: Dict[int, int] = {}
    for allow in (False, True):
        for person in range(len(people_roles)):
            if person not in owner.values():
                _augment(person, lambda p, a=allow: edges(p, a), owner, set())
    missing = Counter(seats[seat] for seat in range(len(seats)) if seat not in owner)
    substituted = sum(1 for seat, person in owner.items() if seats[seat] not in people_roles[person])
    return missing, substituted


def _augment(person: int, edges, owner: Dict[int, int], seen: set) -> bool:
    for seat in edges(person):
        if seat in seen:
            continue
        seen.add(seat)
        if seat not in owner or _augment(owner[seat], edges, owner, seen):
            owner[seat] = person
            return True
    return False
