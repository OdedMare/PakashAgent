"""The rotation's fixed vocabulary: groups, cycles, spans, and date helpers."""

import datetime
from typing import Any, List, Optional

# Group orders per cycle length. Hebrew letters are data here, matching how
# the interview collects them and how `profile_service` validates them.
ROUND_GROUPS = ("א", "ב")
TRIPLET_GROUPS = ("א", "ב", "ג")

# How each cycle is named to a person reading it. The keys are the internal
# pattern names, which no manager should ever be shown.
CYCLE_LABELS = {"round": "סבב", "triplet": "תלתון"}

# Patterns that place a person in a lettered group. `hamshushim` and
# `shushim` describe a closure's span, not its owner, so a person on one of
# them may be ungrouped and still close.
GROUPED_PATTERNS = frozenset({"round", "triplet"})

# How many days before Saturday each pattern's closure begins. Thursday is 2
# days before Saturday, Friday is 1. `round` and `triplet` lead by two like a
# חמשוש: a closure weekend in an Israeli unit runs Thursday to Sunday morning.
CLOSURE_LEAD_DAYS = {"round": 2, "triplet": 2, "hamshushim": 2, "shushim": 1}

# How many days past Saturday a closure runs. One, and only until that day's
# handover. Shared by every pattern: they differ in when the stretch begins,
# never in when it ends.
HANDOVER_TAIL_DAYS = 1

# `datetime.date.weekday()` numbering: Monday is 0, so Saturday is 5.
_SATURDAY = 5


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def parse_date(value: Any) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(text(value))
    except (TypeError, ValueError):
        return None


def saturday_of(day: datetime.date) -> datetime.date:
    """The Saturday closing the week `day` falls in.

    The Israeli week runs Sunday to Saturday, so every day from Sunday onward
    looks forward to the coming Saturday, and Saturday is its own.
    """
    return day + datetime.timedelta(days=(_SATURDAY - day.weekday()) % 7)


def minutes(value: Any) -> Optional[int]:
    """A declared start time as minutes past midnight, or None if unusable.

    Only enough parsing to order shifts against each other.
    """
    stated = text(value)
    if not stated:
        return None
    parts = stated.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        return None
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        return None
    return hour * 60 + minute


def people(profile: dict) -> List[dict]:
    """The roster rows a cycle can speak about — the ones carrying a name."""
    return [
        person for person in (profile or {}).get("employees") or []
        if isinstance(person, dict) and text(person.get("name"))
    ]


def groups_for(pattern: str) -> Optional[tuple]:
    """The lettered groups belonging to one pattern, or None if it has none.

    Strictly per pattern: a round pair does not close one weekend in three.
    """
    if pattern == "triplet":
        return TRIPLET_GROUPS
    if pattern == "round":
        return ROUND_GROUPS
    return None


def cycle_of_group(profile: dict, group: str) -> str:
    """Which cycle a span pattern's group belongs to.

    `ג` can only be a תלתון group; otherwise the unit's own `rotation_mode`
    decides, because that is the cycle the manager set the unit to.
    """
    if group == "ג":
        return "triplet"
    mode = text(((profile or {}).get("workplace") or {}).get("rotation_mode"))
    return mode if mode in GROUPED_PATTERNS else "round"


def exit_pattern(profile: dict, person: dict) -> str:
    """A person's own pattern, falling back to the workplace's rotation mode.

    Per-person first, deliberately: a reserve soldier on חמשושים inside a
    תלתון unit is the normal case, not an exception.
    """
    pattern = text((person or {}).get("exit_pattern"))
    if pattern:
        return pattern
    workplace = (profile or {}).get("workplace") or {}
    return text(workplace.get("rotation_mode")) or "round"


def label(cycle: str, group: str) -> str:
    """One closing group named the way the manager says it: `סבב א`.

    The internal pattern name never leaves this package, so the vocabulary
    cannot drift between the screens that show the same closure.
    """
    group = text(group)
    if not group:
        return ""
    return "%s %s" % (CYCLE_LABELS.get(text(cycle), "סבב"), group)
