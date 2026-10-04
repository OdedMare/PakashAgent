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

| Module | Owns |
|---|---|
| `hypothetical.py` | Applying operations to an in-memory copy |
| `impact.py` | Coverage, workload, who is touched |
"""

from typing import List, Optional

from app.bl.audit import audit, fairness
from app.bl.scheduler import effective_availability
from app.bl.simulate.hypothetical import Hypothetical, iso, schedule_rows
from app.bl.simulate.impact import coverage, touched, warning_key, workload

# Imported by the staffing edge-case tests, which check the seat count here
# agrees with the audit's.
_coverage = coverage


def simulate(
    schedule: dict,
    profile: dict,
    operations: List[dict],
    availability: Optional[List[dict]] = None,
) -> dict:
    """The period as these operations would leave it. Persists nothing.

    `operations` are `bl/changes`'s vocabulary, so a simulation and the
    proposal it may become describe the change in one language. An operation
    naming a slot the period does not contain is reported as skipped rather
    than dropped, and `applied: False` says nothing could be applied.
    """
    schedule = schedule if isinstance(schedule, dict) else {}
    profile = profile if isinstance(profile, dict) else {}
    availability = effective_availability(
        profile, list(availability or []),
        iso(schedule.get("starts_on")), iso(schedule.get("ends_on")),
    )
    before = schedule_rows(schedule)
    result = Hypothetical(before, schedule).apply_all(operations)
    shifts = [row for row in profile.get("shifts") or [] if isinstance(row, dict)]
    employees = [row for row in profile.get("employees") or [] if isinstance(row, dict)]
    slots = [
        dict(slot, slot_date=iso(slot.get("slot_date")))
        for slot in schedule.get("slots") or [] if isinstance(slot, dict)
    ]
    keyed_before = {warning_key(row): row for row in audit(before, shifts, employees, availability, profile, slots)}
    warnings_after = audit(result.rows, shifts, employees, availability, profile, slots)
    keyed_after = {warning_key(row): row for row in warnings_after}
    fairness_after = fairness(result.rows, shifts, employees)
    people = touched(result.applied)
    return {
        # Never persisted, and said in the payload so a client cannot mistake
        # this for something that landed.
        "simulated": True,
        "applied": bool(result.applied),
        "operations": result.applied,
        "skipped": result.skipped,
        "introduced": [row for key, row in keyed_after.items() if key not in keyed_before],
        "resolved": [row for key, row in keyed_before.items() if key not in keyed_after],
        # The whole resulting list, not only the delta: the manager is looking
        # at the week they would end up with.
        "warnings_after": warnings_after,
        "coverage": coverage(before, result.rows, slots, employees, profile),
        "workload": workload(fairness(before, shifts, employees), fairness_after, people),
        "affected": sorted(people),
        "fairness_after": fairness_after,
    }


__all__ = ["simulate"]
