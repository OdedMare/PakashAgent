"""What a placement would cost, and what else the manager could do instead.

**Pure Python. No LLM call, ever.** This is `audit`'s arithmetic asked a
different question: not "what is wrong with the schedule as stored" but "what
would be wrong with it if this move landed", answered *before* the write so
the board can explain a drag rather than let it fail silently (D3).

**Nothing here blocks.** `check()` returns `blocking: False` on every result.
The refusal-shaped information arrives before the click rather than as a
banner after it — same authority, better timing.

The alternatives are the other half: a manager told "דנה has a constraint that
day — יוסי and רון are both free and qualified" has the answer. Both lists are
derived from the profile and the stored grid, never invented.
"""

from typing import List, Optional

from app.bl.placement import values
from app.bl.placement.alternatives import suggest_alternatives
from app.bl.placement.context import PlacementContext, effective_rows
from app.bl.placement.options import closure_of, employee_options


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

    `moving_assignment_id` is the row being dragged: it comes out of the
    hypothetical before the new one goes in, so a move is checked as a move.
    Returns only the warnings this placement is *responsible for*.
    """
    employee, shift_name = values.text(employee), values.text(shift_name)
    slot_date = values.iso(slot_date)
    rows = effective_rows(schedule, profile, availability, slot_date)
    candidates = employee_options(
        schedule, profile, shift_name, slot_date, rows, moving_assignment_id,
    )
    closure = closure_of(profile, slot_date, shift_name)
    if not employee:
        return {
            "ok": True, "blocking": False, "reasons": [], "warnings": [],
            "eligible": True, "alternatives": {"employees": [], "slots": []},
            "candidates": candidates, "closure": closure,
        }
    verdict = PlacementContext(
        schedule, profile, rows, moving_assignment_id,
    ).verdict(employee, shift_name, slot_date)
    alternatives = suggest_alternatives(
        schedule, profile, employee, shift_name, slot_date,
        availability=rows, moving_assignment_id=moving_assignment_id,
    ) if verdict["reasons"] else {"employees": [], "slots": []}
    return dict(verdict, alternatives=alternatives, candidates=candidates, closure=closure)


__all__ = ["check", "closure_of", "employee_options", "suggest_alternatives"]
