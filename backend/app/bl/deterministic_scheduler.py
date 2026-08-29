"""Fast, deterministic assignment of people into an existing slot grid.

**This is the floor, not the ceiling.** `bl/assignment_agent.py` is what
builds a schedule when a model is configured: the agent reads the same
candidate lists this walks, weighs the workplace's own rules — the ones
nobody can express as arithmetic — and decides. This runs when there is no
model, when the model is unreachable, and when the agent's answer cannot be
used, so a model outage costs the manager judgment rather than a schedule
([D25](../../../docs/DECISIONS.md#d25--the-agent-assigns-the-tools-count-and-the-engine-is-the-floor-)).

What it decides is decided by ranking: scarcest capability first, then the
closing group, then the lightest load, with stable tie breakers so the same
inputs always produce the same schedule. It weighs no rule written in
Hebrew, which is exactly what the agent above it is for.

Legality, ranking and the hour tally come from `bl/assignment_tools.py` and
are the same functions the agent's candidate lists are built from. Two
implementations of "who may stand on this slot" is how a day the manager
rebuilds comes out legal once.
"""

import time
from typing import Dict, List, Optional

from app.bl import rotation
from app.bl.assignment_tools import (
    BLOCKING_CODES,
    COST_CODES,
    already_on,
    assignment,
    candidate_key,
    counted_on,
    counts,
    eligible,
    employees as roster,
    hard_conflict,
    introduces_blocking,
    legal_count,
    reason_for,
    shift_hours,
    text as _text,
    unique,
)
from app.bl.audit import audit, load_history
from app.bl.scheduler import build_slots, effective_availability
from app.common.errors import AgentError


# What this engine will not place, as opposed to what the agent may accept
# with an alert. Wider than `BLOCKING_CODES` on purpose: code choosing on its
# own has no judgment to trade a rule against, so it declines every warning
# it can prove rather than deciding which one is worth it today.
_AVOIDED_CODES = BLOCKING_CODES | COST_CODES


def generate_day(
    profile: dict,
    day: str,
    availability: Optional[List[dict]] = None,
    history: Optional[List[dict]] = None,
    required_assignments: Optional[List[dict]] = None,
    already_scheduled: Optional[List[dict]] = None,
    shift_names: Optional[List[str]] = None,
) -> dict:
    """Fill one date without a model call.

    Required rows are pins. Other rows on this date are rebuilt, while rows
    from previous dates participate in rest, hours and fairness checks.
    """
    started = time.monotonic()
    errors = rotation.configuration_errors(profile)
    if errors:
        raise AgentError(
            "לא ניתן לשבץ לפני השלמת הגדרת הסבבים והתלתונים: %s."
            % "; ".join(errors)
        )

    slots = build_slots(profile, day, day)
    wanted = {_text(name) for name in shift_names or [] if _text(name)}
    if wanted:
        slots = [slot for slot in slots if slot["shift_name"] in wanted]
    if not slots:
        return _result(day, started, [], [], [])

    employees = roster(profile)
    people = {_text(row.get("name")): row for row in employees}
    shifts = (profile or {}).get("shifts") or []
    effective = effective_availability(profile, availability, day, day)
    slot_keys = {(slot["shift_name"], slot["slot_date"]) for slot in slots}

    committed = [assignment(row) for row in already_scheduled or []]
    committed = [row for row in committed if row is not None]
    # A targeted shift rebuild preserves the other shifts on the same date.
    current = [
        row for row in committed
        if row["date"] != day or (row["shift"], row["date"]) not in slot_keys
    ]
    current.extend(_unique_required(
        required_assignments, slots, slot_keys, people, effective, day
    ))

    load_rows = load_history(
        list(history or []) + current, shifts, employees
    )
    loads = {row["employee"]: row["hours"] for row in load_rows}
    notes = []

    # Scarce and specialised slots are filled first. Stable tie breakers make
    # rerunning the same day produce the same result.
    slots.sort(key=lambda slot: (
        legal_count(slot, people, effective),
        not bool(slot.get("required_roles")),
        not bool(slot.get("requires_shift_manager")),
        slot.get("start_time") or "",
        slot["shift_name"],
    ))

    for slot in slots:
        while counted_on(current, slot, people, profile) < max(
            0, int(slot.get("headcount") or 0)
        ):
            candidates = []
            for name, person in people.items():
                if not counts(person, profile) or not eligible(
                    person, slot["shift_name"]
                ):
                    continue
                if already_on(current, name, slot):
                    continue
                row = {
                    "employee": name,
                    "shift": slot["shift_name"],
                    "date": slot["slot_date"],
                    "reason": "",
                }
                if hard_conflict(row, slots, effective):
                    continue
                if introduces_blocking(
                    current, row, shifts, employees, effective, profile,
                    slots, codes=_AVOIDED_CODES,
                ):
                    continue
                candidates.append((
                    candidate_key(current, slot, person, profile,
                                  loads.get(name, 0.0)),
                    row,
                    person,
                ))

            if not candidates:
                notes.append(
                    "לא נמצא שיבוץ חוקי ל%s בתאריך %s; המשמרת נשארה בחוסר."
                    % (slot["shift_name"], day)
                )
                break
            _, chosen, person = min(candidates, key=lambda item: item[0])
            chosen["reason"] = reason_for(profile, person, slot)
            current.append(chosen)
            loads[chosen["employee"]] = loads.get(
                chosen["employee"], 0.0
            ) + shift_hours(shifts, chosen["shift"])

    final = [
        row for row in current
        if row["date"] == day and (row["shift"], row["date"]) in slot_keys
    ]
    warnings = [
        row for row in audit(
            current, shifts, employees, effective, profile, slots
        )
        if row.get("date") in (None, "", day)
    ]
    return _result(day, started, slots, final, notes, warnings)


def _unique_required(
    required_assignments: Optional[List[dict]],
    slots: List[dict],
    slot_keys: set,
    people: Dict[str, dict],
    effective: List[dict],
    day: str,
) -> List[dict]:
    """The manager's pins, refused loudly when one cannot stand."""
    required = []
    for raw in required_assignments or []:
        row = assignment(raw)
        if row is None or (row["shift"], row["date"]) not in slot_keys:
            continue
        if row["employee"] not in people:
            raise AgentError("עובד/ת בשיבוץ החובה לא נמצא/ה בצוות")
        if not eligible(people[row["employee"]], row["shift"]):
            raise AgentError(
                "%s אינו/ה כשיר/ה למשמרת %s"
                % (row["employee"], row["shift"])
            )
        if hard_conflict(row, slots, effective):
            raise AgentError(
                "שיבוץ החובה של %s ב-%s סותר אילוץ קשיח, סבב או תלתון"
                % (row["employee"], day)
            )
        row["reason"] = _text(raw.get("reason")) or "שיבוץ חובה של המנהל"
        required.append(row)
    return unique(required)


def _result(
    day: str, started: float, slots: List[dict], assignments: List[dict],
    notes: List[str], warnings: Optional[List[dict]] = None,
) -> dict:
    warnings = warnings or []
    return {
        "slots": slots,
        "assignments": assignments,
        "notes": notes,
        "summary": "השיבוץ נבנה בקוד לפי זמינות, כשירות, עומס וסבבים מחייבים.",
        "warnings": warnings,
        # Nothing here is the agent's judgment, so nothing here is an alert
        # the agent raised. What this engine could not fill is reported as a
        # note and as the audit's own unfilled warning, exactly as before.
        "alerts": [],
        "metrics": {
            "date": day,
            "status": "complete" if slots else "skipped",
            "duration_ms": int((time.monotonic() - started) * 1000),
            "returned": len(assignments),
            "accepted": len(assignments),
            "rejected": 0,
            "warnings": len(warnings),
            "repaired": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "engine": "deterministic",
        },
    }


__all__ = ["generate_day"]
