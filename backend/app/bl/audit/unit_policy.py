"""A unit's staffing standard: role counts, fallback roles, a cap on the weak,
qualifications and weekly shift limits.

Read by the solver (which states them as constraints and prices) and by
the audit (which reports a schedule that drifted from them), so both use
one arithmetic. Every value is optional; a profile with no `unit_policy`
block and no rated, qualified people behaves exactly as before.

Profile shape::

    unit_policy: {
        "max_weak_per_shift": 1,              # competence "weak" per shift; None = no cap
        "qualification_validity_days": 90,
        "role_fallbacks": {"קב\"ר גיאוגרפי": ["קב\"ר מודיעיני"]},
        "weekly_shifts": {"min": 2, "max": 4},          # service_type "reserve"
        "weekly_shifts_regular": {"min": 3, "max": 5},  # everyone else
    }

    employee: {"competence": "weak"|..., "service_type": "reserve"|...,
               "qualifications": [{"role": "אלחוט", "last_active": "2026-09-01"}]}

`competence` and `service_type` are the roster's own fields (the solver's
competence balance and reservist days read them too, `solver/competence.py`);
this module only adds a cap on the weak and team-wide weekly limits beside
each reservist's own `reserve_days_per_week`.
"""

import datetime
from collections import Counter
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.bl.shared import number, person_roles, text

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


def is_reservist(person: Optional[dict]) -> bool:
    return text((person or {}).get("service_type")) == "reserve"


def weekly_limits(profile: Optional[dict], person: Optional[dict]) -> Tuple[int, Optional[int]]:
    """(min, max) shifts per week for this person; max None means no cap."""
    policy = unit_policy(profile)
    block = None if is_reservist(person) else policy.get("weekly_shifts_regular")
    if not isinstance(block, dict):
        block = policy.get("weekly_shifts")
    if not isinstance(block, dict):
        return 0, None
    low = int(number(block.get("min"), 0))
    high = block.get("max")
    high = int(high) if isinstance(high, (int, float)) and not isinstance(high, bool) else None
    return max(0, low), (max(0, high) if high is not None else None)


def held_roles(person: Optional[dict]) -> Set[str]:
    """Every role a person may fill first-hand: `role`, `roles`, qualifications."""
    return person_roles(person or {})


def unit_week(day: datetime.date) -> datetime.date:
    """The Sunday a unit's week starts on (Sunday to Saturday, as the
    unit plans it; ISO weeks start on Monday and would split a weekend)."""
    return day - datetime.timedelta(days=(day.weekday() + 1) % 7)


def qualification_expired(profile: Optional[dict], person: Optional[dict], role: str,
                          on: datetime.date) -> bool:
    """True when every qualification this person has for `role` is stale.

    A role with no qualification row never expires: the unit did not ask
    to track it. A qualification with no last-active date is stale, as in
    the unit's own sheet.
    """
    rows = [row for row in (person or {}).get("qualifications") or []
            if isinstance(row, dict) and text(row.get("role")) == role]
    if not rows:
        return False
    limit = validity_days(profile)
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
