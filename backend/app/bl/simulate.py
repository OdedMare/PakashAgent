"""What a set of changes would do, computed without making them.

**Pure Python. No LLM call, and no repository.** This module is handed a
stored schedule and a list of operations and returns what the period would
look like if they landed — the new warnings, the ones that would clear, the
coverage that would move, and who would be affected. It writes nothing
because it *can* write nothing: like `bl/changes.py` and `bl/importer.py`, it
is given no repository at all, so "the simulation did not persist" is a
property of the wiring rather than a rule somebody has to remember.

## Why this is not `propose()`

`schedule_service.propose()` already audits a hypothetical: it applies the
model's operations in memory and returns the warnings the result would carry.
That answers *"is this proposal safe"* and it answers it as a footnote to a
proposal the manager is being asked to accept.

A simulation is a different question with a different posture. *"מה יקרה אם
אעביר את דנה לחמישי בערב"* is the manager thinking out loud — they have not
asked for a change, and offering them a confirm button would be answering a
question with a commitment. So this returns an *impact report*: what moves,
what breaks, what gets better, who is touched. The manager may then approve
it, which routes through the ordinary `apply()` path with their reason
attached, or discard it, which costs nothing because nothing happened.

The two are deliberately different shapes in the API and different cards on
the screen. A simulation that looked like a proposal would be a proposal.

## What "impact" means here

Four things, all of them countable and none of them a judgment:

- **`introduced` / `resolved`** — warnings the change would add, and ones it
  would clear. Diffed by `audit.py`'s own identity (code, person, date,
  shift) rather than by message, because `_over_hours` writes the running
  total into its sentence and a person going 46 → 54 hours would otherwise
  read as a brand-new warning instead of the one already standing.
- **`coverage`** — required against assigned, before and after. The number
  the board's own header shows, so a simulation and the grid can never
  disagree about whether a day is staffed.
- **`workload`** — hours per person, before and after, for everyone the
  change touches. This is `audit.fairness()`, which is why "moving דנה adds
  8 hours to יוסי" is the same arithmetic as the warning that would fire at
  the limit.
- **`affected`** — every person whose week changes, including the one being
  taken *off* a shift. A manager reading "who does this touch" is asking
  about people, and the person losing a shift is as affected as the one
  gaining it.

Nothing here decides whether the change is good. It says what it would do.
"""

from typing import Any, Dict, List, Optional

from app.bl.audit import audit, fairness
from app.bl.changes import OP_ASSIGN, OP_REMOVE, OP_SWAP

# How many operations one simulation may carry. The same bound
# `changes._MAX_OPERATIONS` applies to a proposal: a simulation is a proposal
# not yet asked for, and letting it be larger would make "simulate" the way
# to describe a change too big to propose.
_MAX_OPERATIONS = 40


def simulate(
    schedule: dict,
    profile: dict,
    operations: List[dict],
    availability: Optional[List[dict]] = None,
) -> dict:
    """The period as these operations would leave it. Persists nothing.

    `operations` are `bl/changes.py`'s vocabulary — `assign`, `remove`,
    `swap` — so a simulation and the proposal it may become describe the
    change in exactly one language. An operation naming a slot the period
    does not contain is reported as unapplied rather than silently dropped:
    the manager asked what would happen, and "that shift does not exist in
    this week" is the answer.

    Returns `applied: False` when nothing could be applied, which is what
    lets the caller say so instead of rendering an empty impact report as
    though the change were harmless.
    """
    schedule = schedule if isinstance(schedule, dict) else {}
    profile = profile if isinstance(profile, dict) else {}
    availability = list(availability or [])

    before = _rows(schedule)
    after, applied, skipped = _apply_all(before, schedule, operations)

    shifts = _shifts(profile)
    employees = _employees(profile)
    slots = _slots(schedule)

    warnings_before = audit(before, shifts, employees, availability, profile, slots)
    warnings_after = audit(after, shifts, employees, availability, profile, slots)

    keyed_before = {_key(row): row for row in warnings_before}
    keyed_after = {_key(row): row for row in warnings_after}

    fairness_before = fairness(before, shifts, employees)
    fairness_after = fairness(after, shifts, employees)

    touched = _touched(applied)

    return {
        # Never persisted, and said in the payload so a client cannot mistake
        # this for something that landed. The UI renders simulations in their
        # own colour off the back of this field.
        "simulated": True,
        "applied": bool(applied),
        "operations": applied,
        "skipped": skipped,
        "introduced": [
            row for key, row in keyed_after.items() if key not in keyed_before
        ],
        "resolved": [
            row for key, row in keyed_before.items() if key not in keyed_after
        ],
        # The whole resulting warning list, not only the delta. A manager
        # deciding whether to approve is looking at the week they would end
        # up with, and the delta alone hides the ten warnings that were
        # already there.
        "warnings_after": warnings_after,
        "coverage": _coverage(before, after, slots),
        "workload": _workload(fairness_before, fairness_after, touched),
        "affected": sorted(touched),
        "fairness_after": fairness_after,
    }


def _apply_all(
    before: List[dict], schedule: dict, operations: Any
) -> tuple:
    """The operations folded into a copy of the rows. Returns (rows, applied, skipped).

    Works on audit rows rather than on stored assignments because that is
    what `audit()` reads and what nothing can accidentally save: there are no
    row ids in here to hand a repository.
    """
    rows = [dict(row) for row in before]
    applied: List[dict] = []
    skipped: List[dict] = []

    slots = {
        (_text(slot.get("shift_name")), _iso(slot.get("slot_date")))
        for slot in (schedule or {}).get("slots") or []
    }

    for item in (operations if isinstance(operations, list) else [])[:_MAX_OPERATIONS]:
        if not isinstance(item, dict):
            continue
        action = _text(item.get("action"))
        employee = _text(item.get("employee"))
        shift = _text(item.get("shift"))
        date = _iso(item.get("date"))

        if action not in (OP_ASSIGN, OP_REMOVE, OP_SWAP) or not employee or not date:
            skipped.append(dict(item, why="הפעולה אינה שלמה"))
            continue

        if action == OP_REMOVE:
            match = _find(rows, employee, shift, date)
            if match is None:
                skipped.append(dict(item, why="%s לא משובץ/ת שם" % employee))
                continue
            rows.remove(match)
            applied.append(dict(item, action=OP_REMOVE))
            continue

        if action == OP_ASSIGN:
            if slots and (shift, date) not in slots:
                skipped.append(dict(item, why="אין משמרת כזו בתקופה"))
                continue
            rows.append({"employee": employee, "shift": shift, "date": date})
            applied.append(dict(item, action=OP_ASSIGN))
            continue

        # A swap: two people trade the slots they are each already on.
        other = _text(item.get("with_employee"))
        other_shift = _text(item.get("with_shift")) or shift
        other_date = _iso(item.get("with_date")) or date
        first = _find(rows, employee, shift, date)
        second = _find(rows, other, other_shift, other_date)
        if first is None or second is None:
            skipped.append(dict(item, why="אחד מהשניים לא משובץ שם"))
            continue
        first["shift"], first["date"] = other_shift, other_date
        second["shift"], second["date"] = shift, date
        applied.append(dict(item, action=OP_SWAP))

    return rows, applied, skipped


def _coverage(
    before: List[dict], after: List[dict], slots: List[dict]
) -> dict:
    """Required against assigned, before and after.

    Counted per slot and capped at the headcount, so three people on a
    one-person shift is one covered place and two overstaffed — not four
    places filled. `audit._staffing` reports the overstaffing as its own
    warning; double-counting it as coverage would make an unstaffed week look
    fine because somebody was tripled up on Sunday.
    """
    required = sum(int(_number(slot.get("headcount"), 1)) for slot in slots)

    def filled(rows: List[dict]) -> int:
        counts: Dict[tuple, int] = {}
        for row in rows:
            key = (_text(row.get("shift")), _iso(row.get("date")))
            counts[key] = counts.get(key, 0) + 1
        total = 0
        for slot in slots:
            key = (_text(slot.get("shift_name")), _iso(slot.get("slot_date")))
            headcount = int(_number(slot.get("headcount"), 1))
            total += min(counts.get(key, 0), headcount)
        return total

    was = filled(before)
    now = filled(after)
    return {
        "required": required,
        "assigned_before": was,
        "assigned_after": now,
        "delta": now - was,
        "percent_before": _percent(was, required),
        "percent_after": _percent(now, required),
    }


def _workload(
    before: dict, after: dict, touched: set
) -> List[dict]:
    """Hours per affected person, before and after.

    Only the people the change touches. A workload table listing everybody
    would bury the two names that moved among a roster of twenty who did
    not, and the manager is asking what this change does.
    """
    was = {
        _text(row.get("employee")): float(row.get("hours") or 0.0)
        for row in before.get("people") or []
    }
    now = {
        _text(row.get("employee")): float(row.get("hours") or 0.0)
        for row in after.get("people") or []
    }

    rows = []
    for name in sorted(touched):
        start = was.get(name, 0.0)
        end = now.get(name, 0.0)
        rows.append({
            "employee": name,
            "hours_before": round(start, 2),
            "hours_after": round(end, 2),
            "delta": round(end - start, 2),
        })
    return rows


def _touched(applied: List[dict]) -> set:
    """Everybody whose week the applied operations change.

    Includes both halves of a swap and the person a `remove` takes off. The
    one losing a shift is as affected as the one gaining it, and a report
    that named only the arriving person would answer "who is affected" with
    half the answer.
    """
    names = set()
    for item in applied:
        employee = _text(item.get("employee"))
        if employee:
            names.add(employee)
        other = _text(item.get("with_employee"))
        if other:
            names.add(other)
    return names


def _find(
    rows: List[dict], employee: str, shift: str, date: str
) -> Optional[dict]:
    """One person's row on one slot.

    An empty `shift` matches any shift that day — the manager saying "take
    דנה off Thursday" without naming which shift is the ordinary case, and
    demanding the shift name would refuse a sentence the product elsewhere
    accepts.
    """
    for row in rows:
        if _text(row.get("employee")) != employee:
            continue
        if _iso(row.get("date")) != date:
            continue
        if shift and _text(row.get("shift")) != shift:
            continue
        return row
    return None


def _rows(schedule: dict) -> List[dict]:
    return [
        {
            "employee": _text(row.get("employee")),
            "shift": _text(row.get("shift")),
            "date": _iso(row.get("date")),
        }
        for row in (schedule or {}).get("assignments") or []
        if isinstance(row, dict)
    ]


def _slots(schedule: dict) -> List[dict]:
    return [
        dict(slot, slot_date=_iso(slot.get("slot_date")))
        for slot in (schedule or {}).get("slots") or []
        if isinstance(slot, dict)
    ]


def _key(warning: dict) -> tuple:
    """What makes two warnings the same warning.

    `placement._key` verbatim, and for the reason spelled out there: the
    message carries running totals, so diffing on it would report a warning
    that merely got worse as a warning that is new.
    """
    return (
        _text(warning.get("code")),
        _text(warning.get("employee")),
        _iso(warning.get("date")),
        _text(warning.get("shift")),
    )


def _employees(profile: dict) -> List[dict]:
    rows = (profile or {}).get("employees")
    return [row for row in rows or [] if isinstance(row, dict)]


def _shifts(profile: dict) -> List[dict]:
    rows = (profile or {}).get("shifts")
    return [row for row in rows or [] if isinstance(row, dict)]


def _percent(part: int, whole: int) -> int:
    return 100 if whole <= 0 else int(round(100.0 * part / whole))


def _number(value: Any, fallback: float) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _text(value)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["simulate"]
