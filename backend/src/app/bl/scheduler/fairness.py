"""Report avoidable load gaps; the model still chooses every assignment."""

from statistics import pvariance

from app.bl.audit import load_history
from app.bl.audit.roster import index_shifts, rows_of
from app.bl.scheduler.candidates import slot_id
from app.bl.scheduler.quality import no_worse
from app.bl.scheduler.values import MAX_HISTORY_ROWS, bounded_rows


def period_load(span, roster):
    return load_history(roster, span.profile.get("shifts") or [],
                        span.profile.get("employees") or [], slots=span.audit_slots)


def night_load(span, roster, history):
    return load_history(bounded_rows(history, MAX_HISTORY_ROWS) + roster,
                        span.profile.get("shifts") or [],
                        span.profile.get("employees") or [], slots=span.audit_slots)


def load_cost(span, roster, history=None):
    """Current nights first, historical night ties next, then current hours."""
    current = period_load(span, roster)
    recent = night_load(span, roster, history)
    return tuple(pvariance(values) if values else 0 for values in (
        [item["nights"] for item in current],
        [item["nights"] for item in recent],
        [item["hours"] for item in current],
    ))


def uneven_load(span, roster, baseline, history=None):
    """One finding suffices to request a complete, balanced span once.

    A gap counts only when a seat can be transferred without adding audit
    findings. Unavailable people, specialised roles and pins therefore cannot
    create an impossible fairness repair. Night transfers may also exchange
    a day shift to preserve rest and hours. A one-night gap is acceptable;
    history breaks ties between equally balanced current-period rosters.
    """
    loads = {item["employee"]: item for item in period_load(span, roster)}
    recent = {item["employee"]: item for item in night_load(span, roster, history)}
    original_cost = load_cost(span, roster, history)
    pins = {(row["employee"], row["date"], row["shift"]) for row in span.required}
    counting = {item["id"] for item in span.candidates["employees"]
                if item["counts_toward_staffing"]}
    choices = {(slot["slot_date"], slot["shift_name"]):
               [span.candidates["name_by_id"][eid]
                for eid in span.candidates["by_slot"][slot_id(index)] if eid in counting]
               for index, slot in enumerate(span.slots, 1)}
    row_info = {(row["employee"], row["date"], row["shift"]): row
                for row in rows_of(roster, index_shifts(span.profile.get("shifts") or []),
                                   span.audit_slots)}
    # ponytail: bounded spans; reuse the real audit for each possible transfer.
    # Replace with indexed checks only if profiling shows this scan is costly.
    for index, row in sorted(enumerate(roster), key=lambda pair:
            not row_info[(pair[1]["employee"], pair[1]["date"], pair[1]["shift"])]["is_night"]):
        key = (row.get("date"), row.get("shift"))
        name = row.get("employee")
        info = row_info[(name, *key)]
        hours = info["hours"]
        if (name, *key) in pins or name not in choices.get(key, []):
            continue
        for other in choices[key]:
            gap = loads[name]["nights"] - loads[other]["nights"]
            night_gap = info["is_night"] and (gap > 1 or
                (gap == 1 and recent[name]["nights"] - recent[other]["nights"] > 1))
            if not night_gap and (hours <= 0 or
                    loads[name]["hours"] - loads[other]["hours"] <= 2 * hours + 1e-6):
                continue
            if any(item.get("employee") == other and
                   (item.get("date"), item.get("shift")) == key for item in roster):
                continue
            trial = roster[:index] + [dict(row, employee=other)] + roster[index + 1:]
            valid = no_worse(baseline, span.audit(trial))
            if not valid and night_gap:
                for swap_index, swap in enumerate(roster):
                    swap_key = (swap.get("date"), swap.get("shift"))
                    if swap.get("employee") != other or name not in choices.get(swap_key, []):
                        continue
                    if (other, *swap_key) in pins or row_info[(other, *swap_key)]["is_night"]:
                        continue
                    exchanged = list(trial)
                    exchanged[swap_index] = dict(swap, employee=name)
                    if no_worse(baseline, span.audit(exchanged)):
                        trial, valid = exchanged, True
                        break
            if valid and load_cost(span, trial, history) < original_cost:
                if night_gap:
                    return [{
                        "code": "uneven_nights", "severity": "notice", "date": "",
                        "employee": name, "shift": row["shift"],
                        "message": "פער לילות שניתן לצמצם: %s עם %d לילות ו-%s עם %d לילות בתקופה "
                                   "(%d ו-%d כולל היסטוריה). פזר את הלילות למינימום האפשרי לכל עובד; "
                                   "אפשר להחליף משמרת יום ולילה תוך שמירה על כיסוי, מנוחה ושיבוצי חובה."
                                   % (name, loads[name]["nights"], other, loads[other]["nights"],
                                      recent[name]["nights"], recent[other]["nights"]),
                        "details": {"period_nights": loads[name]["nights"],
                                    "alternative_nights": loads[other]["nights"],
                                    "alternative_employee": other},
                    }]
                return [{
                    "code": "uneven_load", "severity": "notice", "date": "",
                    "employee": name, "shift": row["shift"],
                    "message": "פער עומס שניתן לצמצם: %s עם %g שעות ו-%s עם %g שעות בתקופה. "
                               "אזן את שעות התקופה; מותר להשאיר כמה ימי מנוחה רצופים."
                               % (name, loads[name]["hours"], other, loads[other]["hours"]),
                    "details": {"period_hours": loads[name]["hours"], "alternative_hours": loads[other]["hours"],
                                "alternative_employee": other},
                }]
    return []
