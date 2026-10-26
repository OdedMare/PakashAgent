"""Seats a chat change leaves empty, filled by the solver (D34).

The model names who leaves a shift; it never picks who replaces them. A
`changes` plan whose removals leave a slot with fewer people than it had is
handed to the solver over the dates and shifts it touched: every other row
on those is a pin, the rest of the period stands as it is, and the person who
left (and anyone the plan marks unavailable) is a hard `avoid` there. Only
rows the solver places on a vacated slot become new `assign` operations, so
the plan still changes nothing the manager did not ask about. Writes nothing.
"""

from collections import Counter

from app.bl.schedule_service.generation.pins import model_assignment
from app.bl.shared import iso
from app.bl.simulate.hypothetical import schedule_rows
from app.common.errors import AgentError

_REASON = "שובץ על ידי ה-solver למושב שהתפנה"
_UNFILLED = "ה-solver לא מצא מחליף שעומד בכל הכללים עבור: %s"
_FAILED = "לא ניתן היה להשלים את המושבים שהתפנו אוטומטית: %s"


def vacated_slots(before, after, operations):
    """(shift, date) pairs a remove or a swap left with fewer people."""
    had = Counter((row["shift"], row["date"]) for row in before)
    has = Counter((row["shift"], row["date"]) for row in after)
    touched = {(row["shift"], row["date"]) for row in operations
               if row.get("action") in ("remove", "swap")}
    return sorted((slot for slot in touched if has[slot] < had[slot]),
                  key=lambda slot: (slot[1], slot[0]))


def fill_vacancies(scheduler, history, cache, team_id, turn, plan, state, rows):
    """Append the solver's picks for every vacated seat to `plan["operations"]`
    and say in `plan["solver_note"]` what it did. Returns the rows as the
    extended plan would leave them."""
    schedule = state["schedule"] or {}
    vacant = vacated_slots(schedule_rows(schedule), rows, plan["operations"])
    if turn.get("leave_vacant") or not vacant:
        return rows
    first, last = min(day for _, day in vacant), max(day for _, day in vacant)
    shifts = sorted({shift for shift, _ in vacant})
    solved = [row for row in rows if first <= row["date"] <= last and row["shift"] in shifts]
    try:
        generated = scheduler.generate_span(
            state["profile"], first, last, availability=state["availability"],
            history=history.before(team_id, iso(schedule["starts_on"])),
            instructions=turn.get("instructions") or "",
            preferences=state["preferences"], translation_cache=cache,
            required_assignments=solved, shift_names=shifts,
            already_scheduled=[model_assignment(row) for row in rows if row not in solved],
            requests=_avoid(plan, vacant),
        )
    except AgentError as exc:
        plan["solver_note"] = _FAILED % exc
        return rows
    taken = {(row["employee"], row["shift"], row["date"]) for row in rows}
    picks = [
        dict(action="assign", employee=row["employee"], shift=row["shift"],
             date=row["date"], reason=row.get("reason") or _REASON)
        for row in generated["assignments"]
        if (row["shift"], row["date"]) in vacant
        and (row["employee"], row["shift"], row["date"]) not in taken
    ]
    plan["operations"] = plan["operations"] + picks
    plan["solver_note"] = _note(picks, vacant)
    return rows + [dict(employee=row["employee"], shift=row["shift"], date=row["date"])
                   for row in picks]


def _avoid(plan, vacant):
    """Hard avoids: whoever left a vacated slot, and every absence the plan sets."""
    requests = [
        {"kind": "avoid", "employees": [row["employee"]], "shifts": [row["shift"]],
         "dates": [row["date"]], "is_hard": True, "reason": "הוסר/ה מהמשמרת בבקשת המנהל"}
        for row in plan["operations"]
        if row.get("action") == "remove" and (row["shift"], row["date"]) in vacant
    ]
    requests += [
        {"kind": "avoid", "employees": [row["employee"]],
         "shifts": [row["shift"]] if row.get("shift") else [], "dates": [row["date"]],
         "is_hard": True, "reason": row.get("reason") or "לא זמין/ה"}
        for row in plan["constraints"]
        if row.get("action") != "remove" and not row.get("available", False)
    ]
    return requests


def _note(picks, vacant):
    lines = []
    if picks:
        lines = ["ה-solver בחר מחליפים למושבים שהתפנו:"] + [
            "- %s · %s: %s" % (row["date"], row["shift"], row["employee"]) for row in picks
        ]
    filled = Counter((row["shift"], row["date"]) for row in picks)
    left = ["%s · %s" % (day, shift) for shift, day in vacant if not filled[(shift, day)]]
    if left:
        lines.append(_UNFILLED % ", ".join(left))
    return "\n".join(lines)
