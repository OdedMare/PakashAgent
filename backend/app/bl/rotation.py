"""Which closure group is in, on any given date. Pure arithmetic, no model.

A closure (`סגירה`) is not another shift to balance. It is a stretch during
which a group stays in until its next exit, and the whole point of a rotation
is that the stretch belongs to *one* group at a time. Balancing shifts across
groups — handing Saturday to whoever is under quota — is exactly the failure
this module exists to prevent: it equalises a number the manager never asked
to equalise, and breaks the cycle everyone planned their month around.

So the cycle is computed here rather than asked of the model, for the same
reason `audit.py` is code and not a prompt: "which group closes on the
weekend of 12/09" is arithmetic, and an LLM that gets it wrong produces an
answer indistinguishable from a right one
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).

The cycle is anchored, not inferred. `workplace.first_closure_date` and
`workplace.first_closure_group` name one Saturday and who held it; every
other closure follows from counting weeks. Without an anchor there is no
cycle -- this module returns nothing and says why, rather than guessing a
phase and silently shifting everybody's exits by a week.

Four patterns, all anchored to the same Saturday:

- `round`     -- two groups, alternating weekends (א, ב, א, ב …)
- `triplet`   -- three groups, one weekend in three (תלתון: א, ב, ג, א …)
- `hamshushim`-- the closing group stays from Thursday through Saturday
- `shushim`   -- the closing group stays from Friday through Saturday

`round` and `triplet` set *who* closes. `hamshushim` and `shushim` set *how
long* that closure runs, which is why a person carries both a
`rotation_group` and an `exit_pattern`: the group picks the weekend, the
pattern picks the days.

**`round` and `triplet` are separate cycles that run side by side.** One
shift routinely holds a soldier on א/ב next to one on תלתון א/ב/ג, and those
two "א"s are not the same א: a two-group cycle repeats every second weekend,
a three-group cycle every third, so they drift apart and re-align every six.
Collapsing them into one cycle would silently move somebody's exits. Each
pattern is therefore counted on its own, off the one shared anchor -- the
anchor fixes *when* the rotation starts, and each pattern decides how fast it
turns from there.
"""

import datetime
from typing import Any, Dict, List, Optional

# Group orders per cycle length. Hebrew letters are data here, matching how
# the interview collects them and how `profile_service` validates them.
_ROUND_GROUPS = ("א", "ב")
_TRIPLET_GROUPS = ("א", "ב", "ג")

# Patterns that place a person in a lettered group. `hamshushim` and
# `shushim` describe a closure's span, not its owner, so a person on one of
# them may be ungrouped and still close.
_GROUPED_PATTERNS = frozenset({"round", "triplet"})

# How many days before Saturday each pattern's closure begins.
# Thursday is 2 days before Saturday, Friday is 1.
_CLOSURE_LEAD_DAYS = {
    "round": 0,
    "triplet": 0,
    "hamshushim": 2,
    "shushim": 1,
}

# `datetime.date.weekday()` numbering: Monday is 0, so Saturday is 5.
_SATURDAY = 5


def cycle(profile: dict, pattern: str = "round") -> Optional[dict]:
    """One pattern's closure cycle, or None when it is not defined.

    `pattern` selects which cycle: `round` turns every second weekend,
    `triplet` every third. They share the anchor and are otherwise
    independent, so asking for one never perturbs the other.

    None is the honest answer for a workplace that never named an anchor. A
    caller that gets None must leave the rotation alone rather than invent
    one -- an invented phase is worse than no phase, because it looks
    authoritative while putting the wrong group in on the wrong weekend.
    """
    workplace = (profile or {}).get("workplace") or {}
    if not isinstance(workplace, dict):
        return None

    anchor = _parse_date(workplace.get("first_closure_date"))
    if anchor is None:
        return None

    groups = _groups_for(pattern)
    if groups is None:
        return None
    first_group = _text(workplace.get("first_closure_group"))
    # The anchor names the group that held the first closure. When the unit
    # stated it in the other structure's vocabulary -- "ג" for a unit whose
    # mode is round -- it cannot place this cycle, so this cycle starts at
    # its own first group rather than adopting a phase that does not exist.
    if first_group not in groups:
        first_group = groups[0]

    # The anchor names a closure, and a closure is anchored on its Saturday.
    # A manager who types the Thursday of a חמשוש means the same closure, so
    # the date is normalised forward to that weekend's Saturday rather than
    # rejected.
    anchor_saturday = _saturday_of(anchor)
    return {
        "anchor": anchor_saturday.isoformat(),
        "groups": list(groups),
        "first_group": first_group,
        # Where the anchor's group sits in the order, so counting can start
        # from index 0 regardless of which group the manager named first.
        "offset": groups.index(first_group),
        "length": len(groups),
    }


def closing_group(
    profile: dict, day: datetime.date, pattern: str = "round"
) -> Optional[str]:
    """Which group holds `day`'s closure in `pattern`'s cycle.

    Always answered per pattern, because on any given weekend a round unit
    and a triplet cohort each have their own group in.
    """
    state = cycle(profile, pattern)
    if state is None:
        return None
    return _group_for_saturday(state, _saturday_of(day))


def closure_days(
    profile: dict, person: dict, start: datetime.date, end: datetime.date
) -> List[dict]:
    """Every closure day this person owns in the period, in date order.

    One row per day, each naming the weekend it belongs to, so a caller can
    say "this is the Thursday of דנה's חמשוש" rather than only "דנה closes
    that week". Empty when the person is not on a rotation, when the cycle is
    undefined, or when their group simply does not close in this period --
    all three are ordinary, not errors.
    """
    state = cycle(profile)
    if state is None or start > end:
        return []

    pattern = exit_pattern(profile, person)
    lead = _CLOSURE_LEAD_DAYS.get(pattern)
    if lead is None:
        return []

    group = _text(person.get("rotation_group"))
    if pattern in _GROUPED_PATTERNS and group not in state["groups"]:
        # A grouped pattern with no valid group cannot be placed in the
        # cycle. `profile_service` already rejects this on save; here it just
        # means "nothing to claim".
        return []

    rows = []
    # Walk Saturdays from the one covering the first day, so a closure that
    # begins on the Thursday before `start` still contributes its in-period
    # days.
    saturday = _saturday_of(start)
    while saturday - datetime.timedelta(days=lead) <= end:
        owner = _group_for_saturday(state, saturday)
        closes = owner == group if pattern in _GROUPED_PATTERNS else True
        if closes:
            day = saturday - datetime.timedelta(days=lead)
            while day <= saturday:
                if start <= day <= end:
                    rows.append({
                        "date": day.isoformat(),
                        "weekend": saturday.isoformat(),
                        "group": owner,
                        "pattern": pattern,
                        "is_saturday": day == saturday,
                    })
                day += datetime.timedelta(days=1)
        saturday += datetime.timedelta(days=7)
    return rows


def exit_pattern(profile: dict, person: dict) -> str:
    """A person's own pattern, falling back to the workplace's rotation mode.

    Per-person first, deliberately: the scheduler prompt already promises not
    to replace someone's pattern with a workplace-wide default, and a reserve
    or overlap soldier on חמשושים inside a תלתון unit is the normal case, not
    an exception.
    """
    workplace = (profile or {}).get("workplace") or {}
    pattern = _text((person or {}).get("exit_pattern"))
    if pattern:
        return pattern
    return _text(workplace.get("rotation_mode")) or "round"


def schedule_for_model(
    profile: dict, start: datetime.date, end: datetime.date
) -> List[dict]:
    """The period's closures, per weekend, as the model should read them.

    Handed to the scheduler prompt so the model never has to derive a cycle
    it cannot verify. Each row is one weekend: who closes it, and who is
    held on each day of it.
    """
    state = cycle(profile)
    if state is None or start > end:
        return []

    people = [
        person for person in (profile or {}).get("employees") or []
        if isinstance(person, dict) and _text(person.get("name"))
    ]

    by_weekend: Dict[str, dict] = {}
    for person in people:
        for row in closure_days(profile, person, start, end):
            weekend = by_weekend.setdefault(row["weekend"], {
                "weekend": row["weekend"],
                "closing_group": row["group"],
                "days": {},
            })
            weekend["days"].setdefault(row["date"], []).append(
                _text(person.get("name"))
            )

    result = []
    for weekend in sorted(by_weekend.values(), key=lambda item: item["weekend"]):
        result.append({
            "weekend": weekend["weekend"],
            "closing_group": weekend["closing_group"],
            "days": [
                {"date": date, "employees": sorted(names)}
                for date, names in sorted(weekend["days"].items())
            ],
        })
    return result


def _group_for_saturday(state: dict, saturday: datetime.date) -> str:
    anchor = _parse_date(state["anchor"])
    weeks = (saturday - anchor).days // 7
    # Python's modulo is already non-negative for a positive divisor, so
    # weekends before the anchor count backwards correctly without a branch.
    index = (weeks + state["offset"]) % state["length"]
    return state["groups"][index]


def _groups_for(pattern: str) -> Optional[tuple]:
    """The lettered groups belonging to one pattern, or None if it has none.

    Strictly per pattern. An earlier version widened the cycle to the whole
    profile's widest structure, which put a `round` א and a `triplet` א on
    the same three-weekend cycle -- and a round pair does not close one
    weekend in three.
    """
    if pattern == "triplet":
        return _TRIPLET_GROUPS
    if pattern == "round":
        return _ROUND_GROUPS
    return None


def _saturday_of(day: datetime.date) -> datetime.date:
    """The Saturday closing the week `day` falls in.

    The Israeli week runs Sunday to Saturday, so every day from Sunday
    onward looks forward to the coming Saturday, and Saturday is its own.
    """
    return day + datetime.timedelta(days=(_SATURDAY - day.weekday()) % 7)


def _parse_date(value: Any) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(_text(value))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
