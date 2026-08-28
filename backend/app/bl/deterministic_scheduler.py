"""Fast, deterministic assignment of people into an existing slot grid.

Language models can interpret a manager's sentence, but they are a poor
place to perform arithmetic and constraint enforcement. This module owns the
central scheduling loop: the same inputs always produce the same schedule,
and a model outage cannot stop generation.
"""

import datetime
import time
from typing import Any, Dict, List, Optional

from app.bl import rotation
from app.bl.audit import (
    CONSECUTIVE,
    CROSS_ROTATION,
    DOUBLE_BOOKED,
    OVER_HOURS,
    SHORT_REST,
    UNAVAILABLE,
    audit,
    constraint_conflicts,
    load_history,
)
from app.bl.scheduler import build_slots, effective_availability
from app.common.errors import AgentError


_BLOCKING_CODES = frozenset({
    CONSECUTIVE, CROSS_ROTATION, DOUBLE_BOOKED, OVER_HOURS, SHORT_REST,
    UNAVAILABLE,
})


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

    employees = _employees(profile)
    people = {_text(row.get("name")): row for row in employees}
    shifts = (profile or {}).get("shifts") or []
    effective = effective_availability(profile, availability, day, day)
    slot_keys = {(slot["shift_name"], slot["slot_date"]) for slot in slots}

    committed = [_assignment(row) for row in already_scheduled or []]
    committed = [row for row in committed if row is not None]
    # A targeted shift rebuild preserves the other shifts on the same date.
    current = [
        row for row in committed
        if row["date"] != day or (row["shift"], row["date"]) not in slot_keys
    ]
    required = []
    for raw in required_assignments or []:
        row = _assignment(raw)
        if row is None or (row["shift"], row["date"]) not in slot_keys:
            continue
        if row["employee"] not in people:
            raise AgentError("עובד/ת בשיבוץ החובה לא נמצא/ה בצוות")
        if not _eligible(people[row["employee"]], row["shift"]):
            raise AgentError(
                "%s אינו/ה כשיר/ה למשמרת %s"
                % (row["employee"], row["shift"])
            )
        if _hard_conflict(row, slots, effective):
            raise AgentError(
                "שיבוץ החובה של %s ב-%s סותר אילוץ קשיח, סבב או תלתון"
                % (row["employee"], day)
            )
        row["reason"] = _text(raw.get("reason")) or "שיבוץ חובה של המנהל"
        required.append(row)
    current.extend(_unique(required))

    load_rows = load_history(
        list(history or []) + current, shifts, employees
    )
    loads = {row["employee"]: row["hours"] for row in load_rows}
    notes = []
    # A placement changes only that employee's hours/rest/double-booking
    # facts. Cache every other person's legality for this date instead of
    # re-auditing the whole accumulated period once per open seat.
    legal_cache: Dict[tuple, bool] = {}

    # Scarce and specialised slots are filled first. Stable tie breakers make
    # rerunning the same day produce the same result.
    slots.sort(key=lambda slot: (
        _legal_count(slot, people, effective),
        not bool(slot.get("required_roles")),
        not bool(slot.get("requires_shift_manager")),
        slot.get("start_time") or "",
        slot["shift_name"],
    ))

    for slot in slots:
        while _counted_on(current, slot, people, profile) < max(
            0, int(slot.get("headcount") or 0)
        ):
            candidates = []
            for name, person in people.items():
                if not _counts(person, profile) or not _eligible(
                    person, slot["shift_name"]
                ):
                    continue
                if _already_on(current, name, slot):
                    continue
                row = {
                    "employee": name,
                    "shift": slot["shift_name"],
                    "date": slot["slot_date"],
                    "reason": "",
                }
                if _hard_conflict(row, slots, effective):
                    continue
                cache_key = (name, slot["shift_name"], slot["slot_date"])
                legal = legal_cache.get(cache_key)
                if legal is None:
                    legal = not _introduces_blocking(
                        current, row, shifts, employees, effective, profile,
                        slots,
                    )
                    legal_cache[cache_key] = legal
                if not legal:
                    continue
                candidates.append((
                    _candidate_key(current, slot, person, profile,
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
            chosen["reason"] = _reason(profile, person, slot)
            current.append(chosen)
            legal_cache = {
                key: value for key, value in legal_cache.items()
                if key[0] != chosen["employee"]
            }
            loads[chosen["employee"]] = loads.get(
                chosen["employee"], 0.0
            ) + _shift_hours(shifts, chosen["shift"])

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


def _candidate_key(
    rows: List[dict], slot: dict, person: dict, profile: dict, hours: float,
) -> tuple:
    missing_roles = _missing_roles(rows, slot, profile)
    roles = _roles(person)
    manager_missing = bool(slot.get("requires_shift_manager")) and not any(
        _person(profile, row["employee"]).get("is_shift_manager")
        for row in rows if _same_slot(row, slot)
    )
    covers_roles = len(missing_roles.intersection(roles))
    covers_manager = manager_missing and bool(person.get("is_shift_manager"))
    day = datetime.date.fromisoformat(slot["slot_date"])
    closing = rotation.holds(
        profile, person, day, slot["shift_name"]
    )
    # First minimise unmet mandatory capabilities, then prefer the closing
    # group and finally the lightest accumulated load.
    remaining = len(missing_roles) - covers_roles + int(
        manager_missing and not covers_manager
    )
    return (
        remaining, not covers_manager, -covers_roles, not closing,
        float(hours), _text(person.get("name")),
    )


def _introduces_blocking(
    current: List[dict], row: dict, shifts: List[dict], employees: List[dict],
    availability: List[dict], profile: dict, slots: List[dict],
) -> bool:
    warnings = audit(
        current + [row], shifts, employees, availability, profile, slots
    )
    return any(
        item.get("severity") == "warning"
        and item.get("code") in _BLOCKING_CODES
        and item.get("date") in (None, "", row["date"])
        and item.get("employee") in (None, "", row["employee"])
        for item in warnings
    )


def _hard_conflict(row: dict, slots: List[dict], availability: List[dict]) -> bool:
    slot = next(
        (item for item in slots if _same_slot(row, item)), {}
    )
    candidate = dict(
        row,
        start_time=slot.get("start_time"),
        end_time=slot.get("end_time"),
    )
    return any(
        item.get("is_hard", True) is not False
        and constraint_conflicts(candidate, item)
        for item in availability if isinstance(item, dict)
    )


def _legal_count(slot: dict, people: Dict[str, dict], availability: List[dict]) -> int:
    return sum(
        _eligible(person, slot["shift_name"])
        and not _hard_conflict({
            "employee": name,
            "shift": slot["shift_name"],
            "date": slot["slot_date"],
        }, [slot], availability)
        for name, person in people.items()
    )


def _reason(profile: dict, person: dict, slot: dict) -> str:
    day = datetime.date.fromisoformat(slot["slot_date"])
    if rotation.holds(profile, person, day, slot["shift_name"]):
        group = _text(person.get("rotation_group"))
        pattern = rotation.exit_pattern(profile, person)
        cycle = pattern if pattern in ("round", "triplet") else _cycle(
            profile, group
        )
        return "%s סוגר/ת במועד הזה; השיבוץ עומד במחזור המחייב." % (
            rotation.label(cycle, group) or "קבוצת הסגירה"
        )
    if slot.get("requires_shift_manager") and person.get("is_shift_manager"):
        return "שובץ/ה כמפקד/ת המשמרת, לפי זמינות ואיזון עומס."
    matched = sorted(_missing_roles([], slot, profile).intersection(_roles(person)))
    if matched:
        return "שובץ/ה לתפקיד %s, לפי זמינות ואיזון עומס." % ", ".join(matched)
    return "שובץ/ה לפי זמינות, כשירות ואיזון עומס."


def _cycle(profile: dict, group: str) -> str:
    if group == "ג":
        return "triplet"
    mode = _text(((profile or {}).get("workplace") or {}).get("rotation_mode"))
    return mode if mode in ("round", "triplet") else "round"


def _counted_on(rows: List[dict], slot: dict, people: Dict[str, dict], profile: dict) -> int:
    return sum(
        _same_slot(row, slot)
        and _counts(people.get(row["employee"], {}), profile)
        for row in rows
    )


def _missing_roles(rows: List[dict], slot: dict, profile: dict) -> set:
    present = set()
    for row in rows:
        if _same_slot(row, slot):
            present.update(_roles(_person(profile, row["employee"])))
    return set(slot.get("required_roles") or []) - present


def _roles(person: dict) -> set:
    roles = person.get("roles")
    if isinstance(roles, list):
        result = {_text(role) for role in roles if _text(role)}
    else:
        result = set()
    role = _text(person.get("role"))
    if role:
        result.add(role)
    return result


def _counts(person: dict, profile: dict) -> bool:
    explicit = person.get("counts_toward_staffing")
    if isinstance(explicit, bool):
        return explicit
    if not person.get("is_trainee"):
        return True
    policy = (profile or {}).get("training_policy") or {}
    return bool(policy.get("counts_toward_staffing"))


def _eligible(person: dict, shift: str) -> bool:
    allowed = person.get("eligible_shifts")
    return not isinstance(allowed, list) or not allowed or shift in allowed


def _already_on(rows: List[dict], employee: str, slot: dict) -> bool:
    return any(row["employee"] == employee and _same_slot(row, slot) for row in rows)


def _same_slot(row: dict, slot: dict) -> bool:
    return (
        _text(row.get("shift")) == _text(slot.get("shift_name") or slot.get("shift"))
        and _date(row.get("date")) == _date(slot.get("slot_date") or slot.get("date"))
    )


def _person(profile: dict, name: str) -> dict:
    return next(
        (row for row in _employees(profile) if _text(row.get("name")) == name),
        {},
    )


def _employees(profile: dict) -> List[dict]:
    return [
        row for row in (profile or {}).get("employees") or []
        if isinstance(row, dict) and _text(row.get("name"))
    ]


def _assignment(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    employee = _text(raw.get("employee"))
    shift = _text(raw.get("shift") or raw.get("shift_name"))
    date = _date(raw.get("date") or raw.get("slot_date"))
    if not employee or not shift or not date:
        return None
    return {
        "employee": employee,
        "shift": shift,
        "date": date,
        "reason": _text(raw.get("reason")),
    }


def _unique(rows: List[dict]) -> List[dict]:
    result, seen = [], set()
    for row in rows:
        key = (row["employee"], row["shift"], row["date"])
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def _shift_hours(shifts: List[dict], name: str) -> float:
    shift = next(
        (row for row in shifts if isinstance(row, dict) and _text(row.get("name")) == name),
        {},
    )
    try:
        start = datetime.time.fromisoformat(_text(shift.get("start_time")))
        end = datetime.time.fromisoformat(_text(shift.get("end_time")))
    except ValueError:
        return 0.0
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    if minutes <= 0:
        minutes += 24 * 60
    weight = shift.get("hour_weight")
    weight = float(weight) if isinstance(weight, (int, float)) else 1.0
    return round(minutes / 60.0 * weight, 2)


def _date(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _text(value)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["generate_day"]
