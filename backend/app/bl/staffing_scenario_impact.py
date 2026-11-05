"""Diffs and attribution for staffing scenarios."""

from app.bl.audit import counts_toward_staffing
from app.bl.shared import iso, number, text, warning_key


def seat_state(rows, slots, profile):
    people = {text(row.get("name")): row for row in profile.get("employees") or []}
    counts = {}
    for row in rows:
        if counts_toward_staffing(people.get(text(row.get("employee"))), profile):
            key = text(row.get("shift")), iso(row.get("date"))
            counts[key] = counts.get(key, 0) + 1
    gaps, over = [], set()
    for slot in slots:
        key = text(slot.get("shift_name")), iso(slot.get("slot_date"))
        required, assigned = int(number(slot.get("headcount"), 1)), counts.get(key, 0)
        if assigned < required:
            gaps.append({"shift": key[0], "date": key[1], "required": required,
                         "assigned": assigned, "missing": required - assigned})
        elif assigned > required:
            over.add(key)
    gaps.sort(key=lambda row: (-row["missing"], row["date"], row["shift"]))
    return gaps, over


def gap_summary(gaps):
    return {"slots": len(gaps), "people_short": sum(row["missing"] for row in gaps)}


def board_delta(before, after, limit=30):
    old, new = _by_employee(before), _by_employee(after)
    moves, additions, removals, operations = [], [], [], []
    for employee in sorted(set(old) | set(new)):
        left = sorted(old.get(employee, set()) - new.get(employee, set()), key=_row_key)
        joined = sorted(new.get(employee, set()) - old.get(employee, set()), key=_row_key)
        paired = min(len(left), len(joined))
        moves.extend({
            "employee": employee, "from_shift": left[index][0], "from_date": left[index][1],
            "to_shift": joined[index][0], "to_date": joined[index][1],
        } for index in range(paired))
        removals.extend({"employee": employee, "shift": shift, "date": date}
                        for shift, date in left[paired:])
        additions.extend({"employee": employee, "shift": shift, "date": date}
                         for shift, date in joined[paired:])
        operations.extend({"action": "remove", "employee": employee, "shift": shift,
                           "date": date, "reason": "סימולציית כוח אדם"}
                          for shift, date in left)
        operations.extend({"action": "assign", "employee": employee, "shift": shift,
                           "date": date, "reason": "סימולציית כוח אדם"}
                          for shift, date in joined)
    return {
        "moves": moves[:limit], "assignments_added": additions[:limit],
        "assignments_removed": removals[:limit], "operations": operations[:limit * 2],
        "affected": sorted({row["employee"] for row in operations}),
    }


def transfers(before, after, surplus, gaps):
    old, new = _by_employee(before), _by_employee(after)
    result = []
    for employee in sorted(set(old) | set(new)):
        sources = sorted((old.get(employee, set()) - new.get(employee, set())).intersection(surplus))
        targets = sorted((new.get(employee, set()) - old.get(employee, set())).intersection(gaps))
        result.extend({
            "employee": employee, "from_shift": source[0], "from_date": source[1],
            "to_shift": target[0], "to_date": target[1],
        } for source, target in zip(sources, targets))
    return result


def reserve_usage(changes, baseline, scenario):
    before_days, after_days = _days_by_employee(baseline), _days_by_employee(scenario)
    return [dict(
        row, days_in_baseline=len(before_days.get(row["employee"], set())),
        days_in_scenario=len(after_days.get(row["employee"], set())),
        extra_days_used=(len(after_days.get(row["employee"], set()))
                         - len(before_days.get(row["employee"], set()))),
    ) for row in changes]


def warning_diff(before, after):
    old = {warning_key(row): row for row in before or []}
    new = {warning_key(row): row for row in after or []}
    return ([row for key, row in new.items() if key not in old],
            [row for key, row in old.items() if key not in new])


def _by_employee(rows):
    result = {}
    for row in rows:
        name = text(row.get("employee"))
        if name:
            result.setdefault(name, set()).add((text(row.get("shift")), iso(row.get("date"))))
    return result


def _days_by_employee(rows):
    result = {}
    for row in rows:
        name, day = text(row.get("employee")), iso(row.get("date"))
        if name and day:
            result.setdefault(name, set()).add(day)
    return result


def _row_key(row):
    return row[1], row[0]


__all__ = ["board_delta", "gap_summary", "reserve_usage", "seat_state", "transfers", "warning_diff"]
