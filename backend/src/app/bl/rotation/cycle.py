"""One pattern's anchored cycle, and whether a profile can enforce its cycles."""

import datetime
from typing import List, Optional

from app.bl.rotation.vocabulary import (
    CYCLE_LABELS, GROUPED_PATTERNS, cycle_of_group, groups_for, parse_date,
    people, saturday_of, text,
)


def cycle(profile: dict, pattern: str = "round") -> Optional[dict]:
    """One pattern's closure cycle, or None when it is not defined.

    Each pattern reads its own anchor, so asking for one never perturbs the
    other. None is the honest answer for a workplace that never named an
    anchor: an invented phase looks authoritative while putting the wrong
    group in on the wrong weekend.
    """
    workplace = (profile or {}).get("workplace") or {}
    if not isinstance(workplace, dict):
        return None
    anchor = parse_date(_anchored(workplace, pattern, "date"))
    groups = groups_for(pattern)
    if anchor is None or groups is None:
        return None
    first_group = text(_anchored(workplace, pattern, "group"))
    # A group stated in the other structure's vocabulary -- "ג" for a round
    # unit -- cannot place this cycle, so it starts at its own first group.
    if first_group not in groups:
        first_group = groups[0]
    return {
        # A closure is anchored on its Saturday; a manager who typed the
        # Thursday of a חמשוש means the same closure.
        "anchor": saturday_of(anchor).isoformat(),
        "groups": list(groups),
        "first_group": first_group,
        "offset": groups.index(first_group),
        "length": len(groups),
    }


def _anchored(workplace: dict, pattern: str, field: str):
    """A pattern-specific anchor key, else the legacy shared one.

    A pattern-specific key, even when blank, is deliberate: it lets a manager
    anchor one cycle and leave the other undefined.
    """
    key = "%s_first_closure_%s" % (pattern, field)
    if key in workplace:
        return workplace.get(key)
    return workplace.get("first_closure_%s" % field)


def group_for_saturday(state: dict, saturday: datetime.date) -> str:
    weeks = (saturday - parse_date(state["anchor"])).days // 7
    # Python's modulo is non-negative for a positive divisor, so weekends
    # before the anchor count backwards correctly without a branch.
    return state["groups"][(weeks + state["offset"]) % state["length"]]


def closing_group(
    profile: dict, day: datetime.date, pattern: str = "round"
) -> Optional[str]:
    """Which group holds `day`'s closure in `pattern`'s cycle."""
    state = cycle(profile, pattern)
    if state is None:
        return None
    return group_for_saturday(state, saturday_of(day))


def configuration_errors(profile: dict) -> List[str]:
    """Missing facts that make a declared round/triplet unenforceable.

    A lettered group without an anchored cycle leaves the server unable to
    know whose weekend Friday is, so generation and every assignment write
    call this first -- a missing phase never degrades into "no rotation".
    """
    required, errors = set(), []
    workplace = (profile or {}).get("workplace") or {}
    for person in people(profile):
        lookup = _person_errors(profile, workplace, person, errors)
        if lookup:
            required.add(lookup)
    for pattern in sorted(required):
        if cycle(profile, pattern) is None:
            errors.append(
                "לא הוגדר עוגן סגירה ל%s (תאריך וקבוצה ראשונה)"
                % CYCLE_LABELS.get(pattern, "סבב")
            )
    return errors


def _person_errors(profile: dict, workplace: dict, person: dict, errors: List[str]) -> str:
    """Append this person's errors; return the cycle they need anchored."""
    name, group = text(person.get("name")), text(person.get("rotation_group"))
    declared = text(person.get("exit_pattern")) or text(workplace.get("rotation_mode"))
    # Total silence is an ordinary civilian roster, not a declared rotation.
    if not declared and not group:
        return ""
    pattern = declared or cycle_of_group(profile, group)
    if pattern in GROUPED_PATTERNS and not group:
        errors.append(
            "לא הוגדרה קבוצת %s עבור %s" % (CYCLE_LABELS.get(pattern, "סבב"), name)
        )
        return ""
    if not group:
        return ""
    lookup = pattern if pattern in GROUPED_PATTERNS else cycle_of_group(profile, group)
    if group not in (groups_for(lookup) or ()):
        errors.append(
            "הקבוצה %s של %s אינה שייכת ל%s"
            % (group, name, CYCLE_LABELS.get(lookup, "סבב"))
        )
    return lookup
