"""What a placement would cost, and what else the manager could do instead.

**Pure Python. No LLM call, ever.** This is `audit.py`'s arithmetic asked a
different question: not "what is wrong with the schedule as stored" but "what
would be wrong with it if this move landed", answered *before* the write so
the board can explain a drag rather than let it fail silently.

The distinction from `changes.py` is the whole reason this file exists.
`ChangeAgent` reads a sentence and decides what the manager meant — that
needs a model. Deciding whether דנה is already on that slot, whether she has
a constraint against it, and which of her colleagues is free instead is
counting, and counting is code's job
([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
A board whose validation went through the model would be unusable the moment
the model was slow, and every check here is one an LLM gets subtly wrong in a
way that looks exactly like getting it right.

**Nothing here blocks.** `check()` returns `blocking: False` on every result
it can produce, and the field exists to say so rather than to be branched on
before a save. The audit is advisory (D3), the manager decides, and a board
that refused a drop the manager wanted would be `audit.py` given the veto
D3 spent its whole entry refusing to grant. What this buys instead is that
the refusal-shaped information arrives *before* the click rather than as a
warning banner after it — same authority, better timing.

The alternatives are the other half. A manager told "דנה has a constraint
that day" and left there has to go find a replacement by reading the grid;
told "דנה has a constraint that day — יוסי and רון are both free and
qualified", they have the answer. Both lists are derived, never invented:
a qualified employee comes from the profile's own `eligible_shifts`, and a
free slot comes from the stored grid.
"""

import datetime
from typing import Any, Dict, List, Optional

from app.bl.audit import audit
from app.bl.scheduler import effective_availability

# How many alternatives are worth offering. Past a handful the list stops
# being an answer and becomes a second grid to read -- the manager already
# has the board for that. Deliberately small.
_MAX_ALTERNATIVES = 5

# How far either side of the intended date to look for a slot the same person
# could take instead. One week: past that it is not "nearby" and the manager
# is choosing a different week rather than adjusting this one.
_NEARBY_DAYS = 7


def check(
    schedule: dict,
    profile: dict,
    employee: str,
    shift_name: str,
    slot_date: str,
    availability: Optional[List[dict]] = None,
    moving_assignment_id: str = "",
) -> dict:
    """What placing `employee` on this slot would mean. Writes nothing.

    Audits the schedule **as the placement would leave it** — the same shape
    `schedule_service.propose()` uses, computed in memory and never stored.
    `moving_assignment_id` is the row being dragged: it comes out of the
    hypothetical before the new one goes in, so a move is checked as a move
    rather than as a person occupying two slots at once.

    Returns the warnings this placement is *responsible for* — those the
    schedule does not already carry — so a board that is already short-staffed
    on Friday does not report Friday's gap against every unrelated drag.
    """
    employee = _text(employee)
    shift_name = _text(shift_name)
    slot_date = _iso(slot_date)

    shifts = _shifts(profile)
    employees = _employees(profile)
    slots = _slots(schedule)
    availability = _effective_availability(
        schedule, profile, availability, slot_date
    )

    candidates = employee_options(
        schedule, profile, shift_name, slot_date, availability,
        moving_assignment_id,
    )
    if not employee:
        return {
            "ok": True, "blocking": False, "reasons": [], "warnings": [],
            "eligible": True, "alternatives": {"employees": [], "slots": []},
            "candidates": candidates,
        }
    verdict = _verdict(
        schedule, profile, employee, shift_name, slot_date,
        shifts, employees, slots, availability, moving_assignment_id,
    )
    return dict(verdict, alternatives=suggest_alternatives(
        schedule, profile, employee, shift_name, slot_date,
        availability=availability,
        moving_assignment_id=moving_assignment_id,
    ) if verdict["reasons"] else {"employees": [], "slots": []},
        candidates=candidates)


def employee_options(
    schedule: dict,
    profile: dict,
    shift_name: str,
    slot_date: str,
    availability: Optional[List[dict]] = None,
    moving_assignment_id: str = "",
) -> List[dict]:
    """Every roster member for a manual picker, with a concrete why-not."""
    shift_name = _text(shift_name)
    slot_date = _iso(slot_date)
    availability = _effective_availability(
        schedule, profile, availability, slot_date
    )
    load = _hours_by_employee(schedule, profile)
    options = []
    for person in _employees(profile):
        name = _text(person.get("name"))
        if not name:
            continue
        verdict = _verdict(
            schedule, profile, name, shift_name, slot_date,
            _shifts(profile), _employees(profile), _slots(schedule),
            availability, moving_assignment_id,
        )
        options.append({
            "employee": name,
            "available": verdict["ok"],
            "reasons": verdict["reasons"],
            "hours": load.get(name, 0.0),
            "is_shift_manager": bool(person.get("is_shift_manager")),
            "can_train": bool(person.get("can_train")),
        })
    options.sort(key=lambda item: (
        not item["available"], item["hours"], item["employee"]
    ))
    return options


def _verdict(
    schedule: dict,
    profile: dict,
    employee: str,
    shift_name: str,
    slot_date: str,
    shifts: List[dict],
    employees: List[dict],
    slots: List[dict],
    availability: List[dict],
    moving_assignment_id: str,
) -> dict:
    """Whether a placement warns, without looking for a way out.

    Split from `check()` so the alternative search can reuse it. Calling the
    public entry point instead would recurse without end: `check` asks for
    alternatives, and every candidate alternative would ask for its own.
    Filtering candidates is a question about *them*, not about what else the
    manager could do, so this is the half it needs.
    """
    before = _rows(schedule, drop=moving_assignment_id)
    after = before + [{
        "employee": employee, "shift": shift_name, "date": slot_date,
    }]

    existing = _keyed(audit(
        before, shifts, employees, availability, profile, slots
    ))
    resulting = audit(after, shifts, employees, availability, profile, slots)
    # Only what this placement introduced. A warning already true of the
    # stored schedule is the board's standing state, not a consequence of
    # the gesture, and attributing it to the drag would teach the manager to
    # ignore the dialog.
    caused = [row for row in resulting if _key(row) not in existing]

    reasons = [_explain(row) for row in caused]
    eligible = _is_eligible(profile, employee, shift_name)
    if not eligible:
        # Not a warning `audit.py` produces: it audits what a schedule *is*,
        # and eligibility is a fact about the roster rather than about the
        # week. It belongs in the same list because to the manager it is the
        # same kind of information -- a reason this placement is odd.
        reasons.insert(0, (
            "%s לא מוגדר/ת למשמרת %s בפרופיל של מקום העבודה."
            % (employee, shift_name)
        ))

    return {
        "ok": not reasons,
        # Always false. Stated rather than omitted so a caller reading this
        # contract sees that refusing is not on the table (D3).
        "blocking": False,
        "reasons": reasons,
        "warnings": caused,
        "eligible": eligible,
    }


def suggest_alternatives(
    schedule: dict,
    profile: dict,
    employee: str,
    shift_name: str,
    slot_date: str,
    availability: Optional[List[dict]] = None,
    moving_assignment_id: str = "",
) -> dict:
    """Two deterministic ways out of a placement that warns.

    `employees` — who else could take *this* slot: qualified for the shift,
    not already on it, and carrying no warning of their own if placed. Sorted
    by hours already assigned in this period, ascending, so the person with
    the lightest week is offered first. That is the same fairness arithmetic
    `audit.fairness()` does, applied to a choice rather than to a report.

    `slots` — where *this person* could go instead: a slot within a week of
    the intended date that they could fill cleanly. Ordered by distance from
    the date the manager actually wanted, because the nearest alternative is
    the one most likely to still serve whatever they were trying to do.

    Both lists are filtered by re-running `check()` and keeping only the
    clean options. An "alternative" that warns is not an alternative.
    """
    employee = _text(employee)
    shift_name = _text(shift_name)
    slot_date = _iso(slot_date)
    availability = _effective_availability(
        schedule, profile, availability, slot_date
    )

    return {
        "employees": _free_employees(
            schedule, profile, employee, shift_name, slot_date,
            availability, moving_assignment_id,
        ),
        "slots": _nearby_slots(
            schedule, profile, employee, shift_name, slot_date,
            availability, moving_assignment_id,
        ),
    }


def _free_employees(
    schedule: dict,
    profile: dict,
    employee: str,
    shift_name: str,
    slot_date: str,
    availability: List[dict],
    moving_assignment_id: str,
) -> List[dict]:
    """Colleagues who could take this slot with no warning of their own."""
    taken = {
        _text(row.get("employee"))
        for row in _rows(schedule, drop=moving_assignment_id)
        if _text(row.get("shift")) == shift_name
        and _iso(row.get("date")) == slot_date
    }
    load = _hours_by_employee(schedule, profile)

    options = []
    for person in _employees(profile):
        name = _text(person.get("name"))
        if not name or name == employee or name in taken:
            continue
        if not _is_eligible(profile, name, shift_name):
            continue
        if not _clean(
            schedule, profile, name, shift_name, slot_date,
            availability, moving_assignment_id,
        ):
            continue
        options.append({
            "employee": name,
            "hours": load.get(name, 0.0),
            # Said in Hebrew here rather than assembled in the browser: the
            # product's copy is Hebrew data throughout, and a sentence built
            # from fragments in TypeScript is the one place a Latin-script
            # assumption creeps back in.
            "why": "%s פנוי/ה ומוגדר/ת למשמרת (%s שעות בתקופה)." % (
                name, _pretty(load.get(name, 0.0))
            ),
        })

    options.sort(key=lambda item: (item["hours"], item["employee"]))
    return options[:_MAX_ALTERNATIVES]


def _nearby_slots(
    schedule: dict,
    profile: dict,
    employee: str,
    shift_name: str,
    slot_date: str,
    availability: List[dict],
    moving_assignment_id: str,
) -> List[dict]:
    """Slots near the intended date this same person could fill cleanly."""
    wanted = _parse(slot_date)
    if wanted is None:
        return []

    options = []
    for slot in _slots(schedule):
        name = _text(slot.get("shift_name"))
        date = _iso(slot.get("slot_date"))
        if not name or not date:
            continue
        if name == shift_name and date == slot_date:
            continue
        day = _parse(date)
        if day is None or abs((day - wanted).days) > _NEARBY_DAYS:
            continue
        if not _clean(
            schedule, profile, employee, name, date,
            availability, moving_assignment_id,
        ):
            continue
        options.append({
            "shift_name": name,
            "slot_date": date,
            "distance": abs((day - wanted).days),
            "why": "%s ב-%s פנויה עבור %s." % (name, date, employee),
        })

    options.sort(key=lambda item: (
        item["distance"], item["slot_date"], item["shift_name"]
    ))
    return options[:_MAX_ALTERNATIVES]


def _clean(
    schedule: dict,
    profile: dict,
    employee: str,
    shift_name: str,
    slot_date: str,
    availability: List[dict],
    moving_assignment_id: str,
) -> bool:
    """Whether this candidate would warn. The alternatives' only filter.

    Goes through `_verdict` rather than `check` on purpose — see its
    docstring. An option that warns is not an alternative, so a candidate is
    kept only when placing them introduces nothing.
    """
    return _verdict(
        schedule, profile, employee, shift_name, slot_date,
        _shifts(profile), _employees(profile), _slots(schedule),
        availability, moving_assignment_id,
    )["ok"]


def _effective_availability(
    schedule: dict, profile: dict, availability: Optional[List[dict]],
    fallback_day: str,
) -> List[dict]:
    starts_on = _iso((schedule or {}).get("starts_on")) or fallback_day
    ends_on = _iso((schedule or {}).get("ends_on")) or fallback_day
    return effective_availability(
        profile, list(availability or []), starts_on, ends_on
    )


def _explain(warning: dict) -> str:
    """A warning as the sentence the board shows.

    `audit.py` already writes Hebrew, and rewriting it here would be a second
    voice describing the same fact -- the thing `bl/CLAUDE.md` warns about
    for the team message. The message is taken as written.
    """
    return _text(warning.get("message"))


def _is_eligible(profile: dict, employee: str, shift_name: str) -> bool:
    """Whether the profile says this person works this shift.

    A roster that declares no `eligible_shifts` for somebody is saying
    nothing, not saying no: the interview does not force the field, and
    treating silence as a restriction would report every placement in a
    workplace that never answered that question. Absent means unrestricted.
    """
    for person in _employees(profile):
        if _text(person.get("name")) != employee:
            continue
        eligible = person.get("eligible_shifts")
        if not isinstance(eligible, list) or not eligible:
            return True
        return shift_name in [_text(item) for item in eligible]
    # Somebody on the grid the roster no longer carries. Their past shifts
    # are real and this is not the place to relitigate them.
    return True


def _hours_by_employee(schedule: dict, profile: dict) -> Dict[str, float]:
    """Assigned hours per person in this period, by the shift's own length."""
    lengths = {}
    for shift in _shifts(profile):
        name = _text(shift.get("name"))
        if name:
            lengths[name] = _length(shift)

    load: Dict[str, float] = {}
    for person in _employees(profile):
        name = _text(person.get("name"))
        if name:
            load[name] = 0.0
    for row in _rows(schedule):
        name = _text(row.get("employee"))
        if not name:
            continue
        load[name] = load.get(name, 0.0) + lengths.get(
            _text(row.get("shift")), 0.0
        )
    return load


def _length(shift: dict) -> float:
    """A shift's weighted clock length, in hours.

    The same arithmetic `audit._shift_hours` does. Duplicated rather than
    imported because that one is private to the audit's own row shape, and
    reaching into it would couple this module to an internal that is free to
    change. Both read `hour_weight`, which is what makes on-call count
    differently (D9).
    """
    start = _time(shift.get("start_time"))
    end = _time(shift.get("end_time"))
    if start is None or end is None:
        return 0.0
    minutes = (end - start).total_seconds() / 60.0
    if minutes <= 0:
        minutes += 24 * 60.0
    weight = shift.get("hour_weight")
    weight = float(weight) if isinstance(weight, (int, float)) else 1.0
    return round((minutes / 60.0) * weight, 2)


def _rows(schedule: dict, drop: str = "") -> List[dict]:
    """The schedule's assignments as audit rows, optionally without one.

    `drop` is the assignment being moved. Removing it is what makes a move
    check as a move: left in, the person is momentarily in two places and
    every drag would report a double-booking it is about to resolve.
    """
    rows = []
    for row in (schedule or {}).get("assignments") or []:
        if not isinstance(row, dict):
            continue
        if drop and _text(row.get("id")) == drop:
            continue
        rows.append({
            "employee": _text(row.get("employee")),
            "shift": _text(row.get("shift")),
            "date": _iso(row.get("date")),
        })
    return rows


def _slots(schedule: dict) -> List[dict]:
    """The stored grid, dates normalized to ISO strings.

    Passed to `audit()` so an entirely unstaffed shift is still visible —
    a slot with nobody on it leaves no assignment row, which is exactly the
    case the unfilled warning exists for.
    """
    slots = []
    for slot in (schedule or {}).get("slots") or []:
        if not isinstance(slot, dict):
            continue
        slots.append(dict(slot, slot_date=_iso(slot.get("slot_date"))))
    return slots


def _employees(profile: dict) -> List[dict]:
    rows = (profile or {}).get("employees")
    return [row for row in rows or [] if isinstance(row, dict)]


def _shifts(profile: dict) -> List[dict]:
    rows = (profile or {}).get("shifts")
    return [row for row in rows or [] if isinstance(row, dict)]


def _keyed(warnings: List[dict]) -> set:
    return {_key(row) for row in warnings}


def _key(warning: dict) -> tuple:
    """What makes two warnings the same warning.

    The message is deliberately out of it: `_over_hours` writes the running
    total into its sentence, so a placement that pushes somebody from 46 to
    54 hours would otherwise read as a brand-new warning rather than as the
    one already standing. Code, person, date and shift are the identity.
    """
    return (
        _text(warning.get("code")),
        _text(warning.get("employee")),
        _text(warning.get("date")),
        _text(warning.get("shift")),
    )


def _pretty(hours: float) -> str:
    """A round number without its trailing zero. 8.0 reads as 8."""
    return ("%g" % round(hours, 1))


def _time(value: Any) -> Optional[datetime.datetime]:
    text = _text(value)
    for shape in ("%H:%M", "%H:%M:%S", "%H"):
        try:
            return datetime.datetime.strptime(text, shape)
        except ValueError:
            continue
    return None


def _parse(value: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _text(value)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["check", "employee_options", "suggest_alternatives"]
