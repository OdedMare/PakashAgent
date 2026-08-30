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

The cycle is anchored, not inferred. Each grouped pattern may name its own
Saturday and first group through `round_first_closure_*` and
`triplet_first_closure_*`. The legacy `first_closure_*` pair remains a
fallback for profiles created before the cycles could be anchored separately.
Without an anchor for a pattern there is no cycle -- this module returns
nothing rather than guessing a phase and silently shifting exits by a week.

Four patterns, with round and triplet independently anchored:

- `round`     -- two groups, alternating weekends (א, ב, א, ב …)
- `triplet`   -- three groups, one weekend in three (תלתון: א, ב, ג, א …)
- `hamshushim`-- the closing group stays from Thursday (חמשוש)
- `shushim`   -- the closing group stays from Friday (שוש)

`round` and `triplet` set *who* closes. `hamshushim` and `shushim` set *how
long* that closure runs, which is why a person carries both a
`rotation_group` and an `exit_pattern`: the group picks the weekend, the
pattern picks the days.

**A closure weekend here is Thursday to Sunday morning.** That is the
Israeli week, not a parameter: the group goes in on Thursday, holds Friday
and Saturday, and is relieved at the Sunday morning handover -- so a closure
is four calendar dates, the last of them only until its first shift of the
day is over. An earlier version ended the stretch on Saturday night, which
left Sunday morning belonging to nobody: the group that closed was free to
be rostered elsewhere on it and the group still on exit was free to be
rostered *into* it, which is precisely the handover the rotation exists to
order. `shushim` starts a day later and ends at the same handover -- the
span differs at its beginning, never at its end.

The Sunday tail covers **the day's first shift by the clock**, not a shift
named "בוקר": shift vocabulary is per workplace
([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)), so
the handover is found by reading the declared start times and taking the
earliest. A workplace that declared no start times has no clock to read and
its closures simply end on Saturday, which is the honest answer rather than
a Sunday blocked on a guess.

**`round` and `triplet` are separate cycles that run side by side.** One
shift routinely holds a soldier on א/ב next to one on תלתון א/ב/ג, and those
two "א"s are not the same א: a two-group cycle repeats every second weekend,
a three-group cycle every third, so they drift apart and re-align every six.
Collapsing them into one cycle or forcing them onto one anchor would silently
move somebody's exits. Each pattern is therefore counted from its own anchor.
"""

import datetime
from typing import Any, Dict, List, Optional

# Group orders per cycle length. Hebrew letters are data here, matching how
# the interview collects them and how `profile_service` validates them.
_ROUND_GROUPS = ("א", "ב")
_TRIPLET_GROUPS = ("א", "ב", "ג")

# How each cycle is named to a person reading it. The keys are the internal
# pattern names, which no manager should ever be shown.
_CYCLE_LABELS = {"round": "סבב", "triplet": "תלתון"}

# Patterns that place a person in a lettered group. `hamshushim` and
# `shushim` describe a closure's span, not its owner, so a person on one of
# them may be ungrouped and still close.
_GROUPED_PATTERNS = frozenset({"round", "triplet"})

# How many days before Saturday each pattern's closure begins.
# Thursday is 2 days before Saturday, Friday is 1.
#
# `round` and `triplet` lead by two like a חמשוש: a closure weekend in an
# Israeli unit runs Thursday to Sunday morning, and a cycle naming only its
# Saturday was describing a weekend nobody actually works.
_CLOSURE_LEAD_DAYS = {
    "round": 2,
    "triplet": 2,
    "hamshushim": 2,
    "shushim": 1,
}

# How many days past Saturday a closure runs. One, and only until that day's
# handover -- see the module docstring. Shared by every pattern: they differ
# in when the stretch begins, never in when it ends.
_HANDOVER_TAIL_DAYS = 1

# `datetime.date.weekday()` numbering: Monday is 0, so Saturday is 5.
_SATURDAY = 5


def cycle(profile: dict, pattern: str = "round") -> Optional[dict]:
    """One pattern's closure cycle, or None when it is not defined.

    `pattern` selects which cycle: `round` turns every second weekend,
    `triplet` every third. Each reads its own anchor, so asking for one never
    perturbs the other.

    None is the honest answer for a workplace that never named an anchor. A
    caller that gets None must leave the rotation alone rather than invent
    one -- an invented phase is worse than no phase, because it looks
    authoritative while putting the wrong group in on the wrong weekend.
    """
    workplace = (profile or {}).get("workplace") or {}
    if not isinstance(workplace, dict):
        return None

    date_key = "%s_first_closure_date" % pattern
    group_key = "%s_first_closure_group" % pattern
    # A pattern-specific key, even when blank, is deliberate: it lets a
    # manager anchor one cycle and leave the other undefined. Profiles that
    # predate these keys keep their former behaviour through the legacy pair.
    anchor = _parse_date(
        workplace.get(date_key)
        if date_key in workplace else workplace.get("first_closure_date")
    )
    if anchor is None:
        return None

    groups = _groups_for(pattern)
    if groups is None:
        return None
    first_group = _text(
        workplace.get(group_key)
        if group_key in workplace else workplace.get("first_closure_group")
    )
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


def configuration_errors(profile: dict) -> List[str]:
    """Missing facts that make a declared round/triplet unenforceable.

    A lettered group without an anchored cycle is not a soft profile gap: it
    leaves the server unable to know whose weekend Friday or Saturday is.
    Generation and every assignment write call this before changing the
    schedule, so a missing phase can never silently degrade into "no
    rotation".
    """
    required = set()
    errors = []
    workplace = (profile or {}).get("workplace") or {}
    for person in _people(profile):
        name = _text(person.get("name"))
        group = _text(person.get("rotation_group"))
        declared = _text(person.get("exit_pattern")) or _text(
            workplace.get("rotation_mode")
        )
        # `exit_pattern()` deliberately defaults to round for old arithmetic
        # callers. Configuration validation must not interpret total silence
        # as a declared rotation and reject ordinary civilian rosters.
        if not declared and not group:
            continue
        pattern = declared or _cycle_of_group(profile, group)
        if pattern in _GROUPED_PATTERNS and not group:
            errors.append(
                "לא הוגדרה קבוצת %s עבור %s"
                % (_CYCLE_LABELS.get(pattern, "סבב"), name)
            )
            continue
        if not group:
            continue
        lookup = pattern if pattern in _GROUPED_PATTERNS else _cycle_of_group(
            profile, group
        )
        required.add(lookup)
        groups = _groups_for(lookup) or ()
        if group not in groups:
            errors.append(
                "הקבוצה %s של %s אינה שייכת ל%s"
                % (group, name, _CYCLE_LABELS.get(lookup, "סבב"))
            )

    for pattern in sorted(required):
        if cycle(profile, pattern) is None:
            errors.append(
                "לא הוגדר עוגן סגירה ל%s (תאריך וקבוצה ראשונה)"
                % _CYCLE_LABELS.get(pattern, "סבב")
            )
    return errors


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

    Read against *this person's own* pattern, so a תלתון א soldier and a
    round א soldier standing the same shift each get their own weekends
    rather than one being folded into the other's cycle.

    One row per day, each naming the weekend it belongs to, so a caller can
    say "this is the Thursday of דנה's חמשוש" rather than only "דנה closes
    that week". Empty when the person is not on a rotation, when the cycle is
    undefined, or when their group simply does not close in this period --
    all three are ordinary, not errors.

    The last row is the **Sunday handover** (`until_handover`), and it is the
    one row that does not own its whole date: `shifts` names the shift the
    group is held for, and an empty `shifts` on every other row means the
    whole day. A caller that ignores `shifts` blocks a Sunday it should only
    have blocked a morning of.

    **A group is what makes a pattern rotate.** חמשושים and שושים say how
    long a closure runs, not whose turn it is, so a person carrying one with
    *no* group is not in a rotation at all: they go out every Thursday, or
    every Friday, every single week. That is an ordinary arrangement, not a
    missing field, and it needs no anchor -- there is no phase to fix when
    every weekend is theirs. Given a group, the same pattern rotates: they
    take only the weekends their group holds.
    """
    if start > end:
        return []

    pattern = exit_pattern(profile, person)
    lead = _CLOSURE_LEAD_DAYS.get(pattern)
    if lead is None:
        return []

    group = _text(person.get("rotation_group"))
    every_weekend = not group and pattern not in _GROUPED_PATTERNS

    state, lookup = None, ""
    if not every_weekend:
        # Which cycle the group belongs to is read from how many groups the
        # unit runs, since a span pattern does not carry one of its own.
        lookup = pattern if pattern in _GROUPED_PATTERNS else _cycle_of_group(
            profile, group
        )
        state = cycle(profile, lookup)
        if state is None or group not in state["groups"]:
            # No anchored cycle, or a group that does not belong to this
            # person's cycle -- either way there is no weekend to claim.
            # `profile_service` rejects the mismatched case on save; here it
            # is simply "nothing to claim", not an error.
            return []

    handover = handover_shifts(profile)
    tail = _HANDOVER_TAIL_DAYS if handover else 0

    rows = []
    # Walk Saturdays from the one *before* the week the period opens in, so a
    # closure that begins on the Thursday before `start` still contributes
    # its in-period days -- and so a period opening on a Sunday still gets
    # the handover belonging to the weekend that just ended.
    saturday = _saturday_of(start) - datetime.timedelta(days=7)
    while saturday - datetime.timedelta(days=lead) <= end:
        owner = group if every_weekend else _group_for_saturday(state, saturday)
        if every_weekend or owner == group:
            day = saturday - datetime.timedelta(days=lead)
            last = saturday + datetime.timedelta(days=tail)
            while day <= last:
                if start <= day <= end:
                    rows.append({
                        "date": day.isoformat(),
                        "weekend": saturday.isoformat(),
                        "group": owner,
                        "pattern": pattern,
                        "cycle": lookup,
                        "is_saturday": day == saturday,
                        # The Sunday the group is relieved on. It owns only
                        # the handover itself, which is why this row is the
                        # only one naming shifts.
                        "until_handover": day > saturday,
                        "shifts": list(handover) if day > saturday else [],
                    })
                day += datetime.timedelta(days=1)
        saturday += datetime.timedelta(days=7)
    return rows


def handover_shifts(profile: dict) -> List[str]:
    """The shift a closure is handed over on: the earliest one of the day.

    Read off the declared vocabulary's own start times rather than matched
    against a name, because shift names belong to the workplace
    ([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace))
    and a list of Hebrew morning names is exactly the hardcoding that
    decision forbids.

    Ties are kept together: a workplace running two shifts from the same hour
    hands over on both, and picking one of them alphabetically would be a
    guess. A workplace whose shifts carry no times returns nothing, and the
    closure then ends on Saturday -- no clock, no handover.
    """
    earliest, names = None, []
    for shift in (profile or {}).get("shifts") or []:
        if not isinstance(shift, dict):
            continue
        name = _text(shift.get("name"))
        minutes = _minutes(shift.get("start_time"))
        if not name or minutes is None:
            continue
        if earliest is None or minutes < earliest:
            earliest, names = minutes, [name]
        elif minutes == earliest and name not in names:
            names.append(name)
    return names


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


def label(cycle: str, group: str) -> str:
    """One closing group named the way the manager says it: `סבב א`.

    The internal pattern name never leaves this module. Anything rendering a
    closure -- a board column, a placement dialog, an assignment's reason --
    goes through here, so the vocabulary cannot drift between the screens
    that show the same closure.
    """
    group = _text(group)
    if not group:
        return ""
    return "%s %s" % (_CYCLE_LABELS.get(_text(cycle), "סבב"), group)


def by_date(
    profile: dict, start: datetime.date, end: datetime.date
) -> Dict[str, dict]:
    """Every closure *day* in the period: whose it is, and who is held on it.

    The per-date view of the same arithmetic `schedule_for_model` folds by
    weekend. Both exist because they answer different questions: a prompt
    reads a cycle a weekend at a time, while a board column, a placement
    check and a picker all ask "what is true of this one date".

    A date with no entry is an ordinary working day and belongs to nobody --
    the absence is the answer, so callers must not read a missing date as a
    closure with no owner. The whole map is empty for a workplace that never
    anchored a cycle, for the reason `cycle()` returns None: an invented
    phase looks authoritative while putting the wrong group in.
    """
    if start > end:
        return {}

    rows: Dict[str, dict] = {}
    for person in _people(profile):
        name = _text(person.get("name"))
        for row in closure_days(profile, person, start, end):
            entry = rows.setdefault(row["date"], {
                "date": row["date"],
                "weekend": row["weekend"],
                # Keyed by cycle rather than by pattern: a חמשושים א and a
                # round א are the same א on the same cycle, and listing them
                # apart would read as two groups in on one weekend.
                "closing_groups": {},
                "employees": [],
                "shifts": [],
                # A date is a handover only while *every* closure landing on
                # it is one. A שוש starting Friday and a חמשוש already in are
                # both mid-stretch on the same Saturday; a Sunday that is one
                # group's handover and another's full day belongs to the
                # wider claim, or the fuller closure would be cut short.
                "until_handover": True,
            })
            if row["cycle"] and row["group"]:
                entry["closing_groups"][row["cycle"]] = row["group"]
            if name not in entry["employees"]:
                entry["employees"].append(name)
            if not row["until_handover"]:
                entry["until_handover"] = False
                entry["shifts"] = []
            elif entry["until_handover"]:
                for shift in row["shifts"]:
                    if shift not in entry["shifts"]:
                        entry["shifts"].append(shift)

    result = {}
    for date, entry in rows.items():
        groups = [
            {"pattern": cycle, "group": group, "label": label(cycle, group)}
            for cycle, group in sorted(entry["closing_groups"].items())
        ]
        result[date] = {
            "date": date,
            "weekend": entry["weekend"],
            "groups": groups,
            "label": " ו".join(item["label"] for item in groups),
            "employees": sorted(entry["employees"]),
            # Empty means the whole date. Named shifts mean the closure only
            # runs until that morning's handover.
            "shifts": sorted(entry["shifts"]),
            "until_handover": bool(entry["until_handover"]),
        }
    return result


def holds(
    profile: dict, person: dict, day: datetime.date, shift: str = ""
) -> bool:
    """Whether this person's own cycle holds `day`, or `shift` on it.

    The question a placement asks about one name, one date and one shift,
    answered off the person's own pattern so a תלתון soldier is never read
    against the round pair's turn.

    `shift` matters on the Sunday handover and nowhere else: the group is in
    for that morning and out for the rest of the day, so asking about the
    date alone would answer "yes" for a Sunday night they are no longer on.
    Asked with no shift, a handover Sunday counts as held -- the day does
    carry a claim of theirs, and a caller enumerating a person's closure
    dates wants it listed.
    """
    for row in closure_days(profile, person, day, day):
        if not row["until_handover"] or not shift or shift in row["shifts"]:
            return True
    return False


def schedule_for_model(
    profile: dict, start: datetime.date, end: datetime.date
) -> List[dict]:
    """The period's closures, per weekend, as the model should read them.

    Handed to the scheduler prompt so the model never has to derive a cycle
    it cannot verify. Each row is one weekend: which group of each pattern
    closes it, and who is held on each day of it.

    A weekend carries `closing_groups` rather than one group, because a unit
    running both structures has a round group and a triplet group in on the
    very same weekend.
    """
    days = by_date(profile, start, end)
    by_weekend: Dict[str, dict] = {}
    for date in sorted(days):
        day = days[date]
        weekend = by_weekend.setdefault(day["weekend"], {
            "weekend": day["weekend"],
            "closing_groups": {},
            "days": [],
        })
        for item in day["groups"]:
            weekend["closing_groups"][item["pattern"]] = item["group"]
        weekend["days"].append({
            "date": date, "employees": day["employees"],
        })

    return [
        {
            "weekend": weekend["weekend"],
            "closing_groups": [
                {"pattern": pattern, "group": group}
                for pattern, group in sorted(weekend["closing_groups"].items())
            ],
            "days": weekend["days"],
        }
        for weekend in sorted(
            by_weekend.values(), key=lambda item: item["weekend"]
        )
    ]


def _people(profile: dict) -> List[dict]:
    """The roster rows a cycle can speak about — the ones carrying a name."""
    return [
        person for person in (profile or {}).get("employees") or []
        if isinstance(person, dict) and _text(person.get("name"))
    ]


def _group_for_saturday(state: dict, saturday: datetime.date) -> str:
    anchor = _parse_date(state["anchor"])
    weeks = (saturday - anchor).days // 7
    # Python's modulo is already non-negative for a positive divisor, so
    # weekends before the anchor count backwards correctly without a branch.
    index = (weeks + state["offset"]) % state["length"]
    return state["groups"][index]


def _cycle_of_group(profile: dict, group: str) -> str:
    """Which cycle a span pattern's group belongs to.

    A חמשושים person carries a group but not a cycle length. `ג` can only be
    a תלתון group; otherwise the unit's own `rotation_mode` decides, because
    that is the cycle the manager set the rest of the unit to.
    """
    if group == "ג":
        return "triplet"
    workplace = (profile or {}).get("workplace") or {}
    mode = _text(workplace.get("rotation_mode"))
    return mode if mode in _GROUPED_PATTERNS else "round"


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


def _minutes(value: Any) -> Optional[int]:
    """A declared start time as minutes past midnight, or None if unusable.

    Only enough parsing to order shifts against each other; `audit.py` and
    `placement.py` do their own arithmetic on the same field for lengths.
    """
    text = _text(value)
    if not text:
        return None
    parts = text.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        return None
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        return None
    return hour * 60 + minute


def _parse_date(value: Any) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(_text(value))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
