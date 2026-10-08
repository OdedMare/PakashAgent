"""Report avoidable load gaps; the model still chooses every assignment."""

from app.bl.audit import load_history
from app.bl.audit.roster import index_shifts, rows_of
from app.bl.scheduler.candidates import slot_id
from app.bl.scheduler.quality import no_worse


def period_load(span, roster):
    return load_history(roster, span.profile.get("shifts") or [],
                        span.profile.get("employees") or [], slots=span.audit_slots)


def load_cost(span, roster):
    # At fixed coverage, sum of squares falls whenever hours become more equal.
    return sum(item["hours"] ** 2 for item in period_load(span, roster))


def uneven_load(span, roster, baseline):
    """One finding suffices to request a complete, balanced span once.

    A gap counts only when a seat can be transferred without adding audit
    findings. Unavailable people, specialised roles and pins therefore cannot
    create an impossible fairness repair. Only gaps exceeding two of the
    transferable shift's durations buy another model call.
    """
    loads = {item["employee"]: item["hours"] for item in period_load(span, roster)}
    pins = {(row["employee"], row["date"], row["shift"]) for row in span.required}
    counting = {item["id"] for item in span.candidates["employees"]
                if item["counts_toward_staffing"]}
    choices = {(slot["slot_date"], slot["shift_name"]):
               [span.candidates["name_by_id"][eid]
                for eid in span.candidates["by_slot"][slot_id(index)] if eid in counting]
               for index, slot in enumerate(span.slots, 1)}
    hours_by_row = {(row["employee"], row["date"], row["shift"]): row["hours"]
                    for row in rows_of(roster, index_shifts(span.profile.get("shifts") or []),
                                       span.audit_slots)}
    # ponytail: bounded spans; reuse the real audit for each possible transfer.
    # Replace with indexed checks only if profiling shows this scan is costly.
    for index, row in enumerate(roster):
        key = (row.get("date"), row.get("shift"))
        name = row.get("employee")
        hours = hours_by_row.get((name, *key), 0)
        if hours <= 0 or (name, *key) in pins or name not in choices.get(key, []):
            continue
        for other in choices[key]:
            if loads[name] - loads[other] <= 2 * hours + 1e-6:
                continue
            if any(item.get("employee") == other and
                   (item.get("date"), item.get("shift")) == key for item in roster):
                continue
            trial = roster[:index] + [dict(row, employee=other)] + roster[index + 1:]
            if no_worse(baseline, span.audit(trial)):
                return [{
                    "code": "uneven_load", "severity": "notice", "date": "",
                    "employee": name, "shift": row["shift"],
                    "message": "פער עומס שניתן לצמצם: %s עם %g שעות ו-%s עם %g שעות בתקופה. "
                               "אזן את שעות התקופה; מותר להשאיר כמה ימי מנוחה רצופים."
                               % (name, loads[name], other, loads[other]),
                    "details": {"hours": loads[name], "alternative_hours": loads[other],
                                "alternative_employee": other},
                }]
    return []
