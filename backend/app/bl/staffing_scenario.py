"""Compare a staffing what-if with the best result the current roster can reach.

The solver works on copies only.  This module has no repository and therefore
cannot save the hypothetical reservist days, extra staff or assignments.
"""

import copy
from typing import List, Optional

from app.bl.audit import counts_toward_staffing
from app.bl.shared import iso, number, text
from app.bl.simulate.hypothetical import schedule_rows
from app.bl.simulate.impact import coverage
from app.bl.solver.problem import Problem
from app.bl.solver.solve import solve
from app.common.errors import AgentError

_MAX_ADDITIONAL_STAFF = 20
_MAX_ROWS = 30
_SERVICE_TYPES = {"standard", "reserve", "civilian", "hatzach"}
_COMPETENCE = {"", "weak", "medium", "high", "excellent"}


def analyze(
    schedule: dict,
    profile: dict,
    *,
    reserve_days_per_week: Optional[int] = None,
    reserve_min_days: Optional[int] = None,
    employee: str = "",
    additional_staff: Optional[List[dict]] = None,
    availability: Optional[List[dict]] = None,
    history: Optional[List[dict]] = None,
    duties: Optional[List[dict]] = None,
    time_limit: float = 5.0,
    workers: int = 2,
) -> dict:
    """Solve the current roster, then solve the requested staffing scenario.

    The first solve separates capacity already present in the roster from the
    improvement caused by the hypothetical change.  Both preserve as much of
    the current board as coverage and the saved rules allow.
    """
    current_profile = copy.deepcopy(profile or {})
    scenario_profile = copy.deepcopy(current_profile)
    slots = [dict(row, slot_date=iso(row.get("slot_date")))
             for row in (schedule or {}).get("slots") or []]
    if not slots:
        raise AgentError("אין משמרות בסידור שנבחר")
    before = schedule_rows(schedule)
    reserve_changes = _reserve_changes(
        scenario_profile, reserve_days_per_week, reserve_min_days, employee,
    )
    added = _additional_staff(scenario_profile, additional_staff or [])
    changed = bool(reserve_changes or added)

    baseline = _solve(
        current_profile, slots, before, availability, history, duties,
        time_limit, workers,
    )
    scenario = _solve(
        scenario_profile, slots, before, availability, history, duties,
        time_limit, workers,
    ) if changed else baseline

    baseline_coverage = coverage(
        before, baseline["assignments"], slots,
        current_profile.get("employees") or [], current_profile,
    )
    scenario_coverage = coverage(
        before, scenario["assignments"], slots,
        scenario_profile.get("employees") or [], scenario_profile,
    )
    current_gaps, current_over = _seat_state(before, slots, current_profile)
    balanced_gaps, _ = _seat_state(baseline["assignments"], slots, current_profile)
    scenario_gaps, _ = _seat_state(scenario["assignments"], slots, scenario_profile)
    moves, additions, removals = _changes(before, scenario["assignments"])
    current_gap_keys = {(row["shift"], row["date"]) for row in current_gaps}
    transfers = _transfers(
        before, scenario["assignments"], current_over, current_gap_keys,
    )

    return {
        "simulated": True,
        "applied": False,
        "schedule_id": text((schedule or {}).get("id")),
        "coverage": {
            "required": scenario_coverage["required"],
            "current_assigned": scenario_coverage["assigned_before"],
            "current_percent": scenario_coverage["percent_before"],
            "after_rebalance": baseline_coverage["assigned_after"],
            "after_rebalance_percent": baseline_coverage["percent_after"],
            "after_scenario": scenario_coverage["assigned_after"],
            "after_scenario_percent": scenario_coverage["percent_after"],
            "delta_from_current": scenario_coverage["delta"],
            "scenario_gain": (
                scenario_coverage["assigned_after"] - baseline_coverage["assigned_after"]
            ),
        },
        "gaps_current": current_gaps[:_MAX_ROWS],
        "gaps_after_rebalance": balanced_gaps[:_MAX_ROWS],
        "gaps_after_scenario": scenario_gaps[:_MAX_ROWS],
        "gap_summary": {
            "current": _gap_summary(current_gaps),
            "after_rebalance": _gap_summary(balanced_gaps),
            "after_scenario": _gap_summary(scenario_gaps),
        },
        "moves": moves[:_MAX_ROWS],
        "transfers_from_surplus": transfers[:_MAX_ROWS],
        "assignments_added": additions[:_MAX_ROWS],
        "assignments_removed": removals[:_MAX_ROWS],
        "reserve_changes": reserve_changes,
        "additional_staff": added,
        "warnings_after": scenario.get("warnings") or [],
        "notes": scenario.get("notes") or [],
        "assumptions": [
            "התרחיש אוכף את התקינה, הכשירויות, הסבבים, המנוחה והאילוצים השמורים.",
            "עובדי תרחיש הם קיבולת היפותטית בלבד; לפני הוספה אמיתית נדרשים שמות ופרטי עובד מלאים.",
            "הנחיות טקסט חופשיות והעדפות שלא תורגמו לכלל מובנה אינן מחושבות מחדש בתרחיש.",
        ],
    }


def _solve(profile, slots, keep, availability, history, duties, time_limit, workers):
    problem = Problem(
        profile, slots, availability=availability, history=history,
        keep=keep, duties=duties,
    )
    return solve(problem, time_limit=time_limit, workers=workers)


def _reserve_changes(profile, days, minimum, employee):
    if days is None and minimum is None:
        return []
    days = _week_days(days, "מספר ימי המילואים") if days is not None else None
    minimum = _week_days(minimum, "מינימום ימי המילואים") if minimum is not None else None
    people = profile.get("employees") or []
    selected = [row for row in people if text(row.get("service_type")) == "reserve"
                and (not employee or text(row.get("name")) == text(employee))]
    if not selected:
        raise AgentError("לא נמצא איש מילואים מתאים לתרחיש")
    changes = []
    for person in selected:
        cap = days if days is not None else _week_days(
            person.get("reserve_days_per_week"), "מספר ימי המילואים",
        )
        floor = minimum if minimum is not None else person.get("reserve_min_days")
        if floor not in (None, "") and _week_days(floor, "מינימום ימי המילואים") > cap:
            raise AgentError("מינימום ימי המילואים אינו יכול להיות גבוה ממספר הימים המרבי")
        before = {
            "reserve_days_per_week": person.get("reserve_days_per_week"),
            "reserve_min_days": person.get("reserve_min_days"),
        }
        if days is not None:
            person["reserve_days_per_week"] = days
        if minimum is not None:
            person["reserve_min_days"] = minimum
        changes.append({
            "employee": text(person.get("name")), "before": before,
            "after": {
                "reserve_days_per_week": person.get("reserve_days_per_week"),
                "reserve_min_days": person.get("reserve_min_days"),
            },
        })
    return changes


def _week_days(value, label):
    if isinstance(value, bool):
        raise AgentError(label + " חייב להיות מספר בין 1 ל-7")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise AgentError(label + " חייב להיות מספר בין 1 ל-7") from exc
    if not 1 <= result <= 7:
        raise AgentError(label + " חייב להיות מספר בין 1 ל-7")
    return result


def _additional_staff(profile, groups):
    if not isinstance(groups, list):
        raise AgentError("תוספת כוח האדם לתרחיש אינה תקינה")
    shifts = {text(row.get("name")) for row in profile.get("shifts") or []}
    existing = {text(row.get("name")) for row in profile.get("employees") or []}
    total, added = 0, []
    for group_index, raw in enumerate(groups, start=1):
        if not isinstance(raw, dict):
            raise AgentError("כל קבוצת כוח אדם בתרחיש חייבת לכלול סוג שירות ומשמרות")
        try:
            count = int(raw.get("count") or 0)
        except (TypeError, ValueError) as exc:
            raise AgentError("כמות כוח האדם בתרחיש חייבת להיות מספר") from exc
        service_type = text(raw.get("service_type"))
        eligible = list(dict.fromkeys(text(item) for item in raw.get("eligible_shifts") or [] if text(item)))
        competence = text(raw.get("competence"))
        if count < 1 or total + count > _MAX_ADDITIONAL_STAFF:
            raise AgentError("אפשר לבדוק עד 20 אנשי צוות נוספים בתרחיש")
        if service_type not in _SERVICE_TYPES or not eligible or not set(eligible).issubset(shifts):
            raise AgentError("יש לציין סוג שירות ומשמרות מוכרות לכל כוח אדם נוסף")
        if competence not in _COMPETENCE:
            raise AgentError("הרמה המקצועית בתרחיש אינה מוכרת")
        reserve_days = raw.get("reserve_days_per_week")
        if service_type == "reserve":
            reserve_days = _week_days(reserve_days, "מספר ימי המילואים של כוח האדם הנוסף")
        total += count
        names = []
        for member in range(1, count + 1):
            base = "כוח תרחיש %d-%d" % (group_index, member)
            name = base
            suffix = 2
            while name in existing:
                name, suffix = "%s (%d)" % (base, suffix), suffix + 1
            existing.add(name)
            person = {
                "name": name,
                "role": text(raw.get("role")),
                "eligible_shifts": eligible,
                "service_type": service_type,
                "exit_pattern": "none",
                "rotation_group": "",
                "counts_toward_staffing": True,
                "competence": competence,
            }
            if service_type == "reserve":
                person["reserve_days_per_week"] = reserve_days
            profile.setdefault("employees", []).append(person)
            names.append(name)
        added.append({
            "count": count, "service_type": service_type,
            "role": text(raw.get("role")), "eligible_shifts": eligible,
            "competence": competence, "reserve_days_per_week": reserve_days,
            "scenario_names": names,
        })
    return added


def _seat_state(rows, slots, profile):
    people = {text(row.get("name")): row for row in profile.get("employees") or []}
    counts = {}
    for row in rows:
        if counts_toward_staffing(people.get(text(row.get("employee"))), profile):
            key = (text(row.get("shift")), iso(row.get("date")))
            counts[key] = counts.get(key, 0) + 1
    gaps, over = [], set()
    for slot in slots:
        key = text(slot.get("shift_name")), iso(slot.get("slot_date"))
        required = int(number(slot.get("headcount"), 1))
        assigned = counts.get(key, 0)
        if assigned < required:
            gaps.append({
                "shift": key[0], "date": key[1], "required": required,
                "assigned": assigned, "missing": required - assigned,
            })
        elif assigned > required:
            over.add(key)
    gaps.sort(key=lambda row: (-row["missing"], row["date"], row["shift"]))
    return gaps, over


def _changes(before, after):
    old, new = _by_employee(before), _by_employee(after)
    moves, additions, removals = [], [], []
    for employee in sorted(set(old) | set(new)):
        left = sorted(old.get(employee, set()) - new.get(employee, set()), key=lambda row: (row[1], row[0]))
        joined = sorted(new.get(employee, set()) - old.get(employee, set()), key=lambda row: (row[1], row[0]))
        paired = min(len(left), len(joined))
        moves.extend({
            "employee": employee,
            "from_shift": left[index][0], "from_date": left[index][1],
            "to_shift": joined[index][0], "to_date": joined[index][1],
        } for index in range(paired))
        removals.extend({"employee": employee, "shift": shift, "date": date}
                        for shift, date in left[paired:])
        additions.extend({"employee": employee, "shift": shift, "date": date}
                         for shift, date in joined[paired:])
    return moves, additions, removals


def _gap_summary(gaps):
    return {"slots": len(gaps), "people_short": sum(row["missing"] for row in gaps)}


def _transfers(before, after, surplus, gaps):
    old, new = _by_employee(before), _by_employee(after)
    result = []
    for employee in sorted(set(old) | set(new)):
        sources = sorted((old.get(employee, set()) - new.get(employee, set())).intersection(surplus))
        targets = sorted((new.get(employee, set()) - old.get(employee, set())).intersection(gaps))
        result.extend({
            "employee": employee,
            "from_shift": source[0], "from_date": source[1],
            "to_shift": target[0], "to_date": target[1],
        } for source, target in zip(sources, targets))
    return result


def _by_employee(rows):
    result = {}
    for row in rows:
        name = text(row.get("employee"))
        if name:
            result.setdefault(name, set()).add((text(row.get("shift")), iso(row.get("date"))))
    return result


__all__ = ["analyze"]
