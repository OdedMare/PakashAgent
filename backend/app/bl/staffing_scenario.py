"""Compare a staffing what-if with the current roster's best result.

The solver works on copies only. This module has no repository and therefore
cannot save hypothetical reservist capacity, extra staff or assignments.
"""

import copy
from typing import List, Optional

from app.bl.audit import fairness
from app.bl.shared import iso, text
from app.bl.simulate.hypothetical import schedule_rows
from app.bl.simulate.impact import coverage, workload
from app.bl.solver.problem import Problem
from app.bl.solver.solve import solve
from app.bl.staffing_scenario_impact import (
    board_delta, gap_summary, reserve_usage, seat_state, transfers, warning_diff,
)
from app.bl.staffing_scenario_people import additional_staff as add_staff, reserve_changes
from app.common.errors import AgentError

_MAX_ROWS = 30


def analyze(
    schedule: dict,
    profile: dict,
    *,
    reserve_days_per_week: Optional[int] = None,
    reserve_min_days: Optional[int] = None,
    reserve_extra_days: Optional[int] = None,
    employee: str = "",
    additional_staff: Optional[List[dict]] = None,
    availability: Optional[List[dict]] = None,
    history: Optional[List[dict]] = None,
    duties: Optional[List[dict]] = None,
    time_limit: float = 5.0,
    workers: int = 2,
) -> dict:
    """Solve the current roster, then the requested staffing scenario."""
    current_profile = copy.deepcopy(profile or {})
    scenario_profile = copy.deepcopy(current_profile)
    slots = [dict(row, slot_date=iso(row.get("slot_date")))
             for row in (schedule or {}).get("slots") or []]
    if not slots:
        raise AgentError("אין משמרות בסידור שנבחר")
    before = schedule_rows(schedule)
    changed_reserve = reserve_changes(
        scenario_profile, reserve_days_per_week, reserve_min_days,
        reserve_extra_days, employee,
    )
    added = add_staff(scenario_profile, additional_staff or [])
    changed = any(row["changed"] for row in changed_reserve) or bool(added)
    baseline = _solve(current_profile, slots, before, availability, history, duties,
                      time_limit, workers)
    scenario = _solve(scenario_profile, slots, before, availability, history, duties,
                      time_limit, workers) if changed else baseline
    return _report(
        schedule, current_profile, scenario_profile, slots, before,
        baseline, scenario, changed_reserve, added, reserve_extra_days, employee,
    )


def _solve(profile, slots, keep, availability, history, duties, time_limit, workers):
    problem = Problem(profile, slots, availability=availability, history=history,
                      keep=keep, duties=duties)
    return solve(problem, time_limit=time_limit, workers=workers)


def _report(schedule, current_profile, scenario_profile, slots, before,
            baseline, scenario, changed_reserve, added, extra, employee):
    baseline_coverage = coverage(
        before, baseline["assignments"], slots,
        current_profile.get("employees") or [], current_profile,
    )
    scenario_coverage = coverage(
        before, scenario["assignments"], slots,
        scenario_profile.get("employees") or [], scenario_profile,
    )
    current_gaps, current_over = seat_state(before, slots, current_profile)
    balanced_gaps, _ = seat_state(baseline["assignments"], slots, current_profile)
    scenario_gaps, _ = seat_state(scenario["assignments"], slots, scenario_profile)
    from_current = board_delta(before, scenario["assignments"], _MAX_ROWS)
    caused = board_delta(baseline["assignments"], scenario["assignments"], _MAX_ROWS)
    introduced, resolved = warning_diff(baseline.get("warnings"), scenario.get("warnings"))
    return {
        "simulated": True, "applied": False,
        "schedule_id": text((schedule or {}).get("id")),
        "scenario": _scenario(changed_reserve, added, extra, employee),
        "coverage": _coverage_report(baseline_coverage, scenario_coverage),
        "gaps_current": current_gaps[:_MAX_ROWS],
        "gaps_after_rebalance": balanced_gaps[:_MAX_ROWS],
        "gaps_after_scenario": scenario_gaps[:_MAX_ROWS],
        "gap_summary": {
            "current": gap_summary(current_gaps),
            "after_rebalance": gap_summary(balanced_gaps),
            "after_scenario": gap_summary(scenario_gaps),
        },
        "moves": from_current["moves"],
        "transfers_from_surplus": transfers(
            before, scenario["assignments"], current_over,
            {(row["shift"], row["date"]) for row in current_gaps},
        )[:_MAX_ROWS],
        "assignments_added": from_current["assignments_added"],
        "assignments_removed": from_current["assignments_removed"],
        "board_delta": {"from_current": from_current, "caused_by_scenario": caused},
        "reserve_changes": reserve_usage(
            changed_reserve, baseline["assignments"], scenario["assignments"],
        ),
        "additional_staff": added, "introduced": introduced, "resolved": resolved,
        "warnings_after": scenario.get("warnings") or [],
        "workload": _workload(current_profile, scenario_profile, baseline, scenario, caused),
        "notes": scenario.get("notes") or [], "assumptions": _assumptions(),
    }


def _coverage_report(baseline, scenario):
    return {
        "required": scenario["required"],
        "current_assigned": scenario["assigned_before"],
        "current_percent": scenario["percent_before"],
        "after_rebalance": baseline["assigned_after"],
        "after_rebalance_percent": baseline["percent_after"],
        "after_scenario": scenario["assigned_after"],
        "after_scenario_percent": scenario["percent_after"],
        "delta_from_current": scenario["delta"],
        "scenario_gain": scenario["assigned_after"] - baseline["assigned_after"],
    }


def _scenario(changed_reserve, added, extra, employee):
    return {
        "kind": "reserve_capacity" if changed_reserve else "additional_staff" if added else "rebalance",
        "extra_days": extra,
        "scope": "employee" if employee else "all_reservists",
        "employee": text(employee),
    }


def _workload(current_profile, scenario_profile, baseline, scenario, caused):
    return workload(
        fairness(baseline["assignments"], current_profile.get("shifts") or [],
                 current_profile.get("employees") or []),
        fairness(scenario["assignments"], scenario_profile.get("shifts") or [],
                 scenario_profile.get("employees") or []),
        set(caused["affected"]),
    )


def _assumptions():
    return [
        "התרחיש אוכף את התקינה, הכשירויות, הסבבים, המנוחה והאילוצים השמורים.",
        "עובדי תרחיש הם קיבולת היפותטית בלבד; לפני הוספה אמיתית נדרשים שמות ופרטי עובד מלאים.",
        "תוספת ימי מילואים מגדילה את התקרה בלבד; היא אינה מחייבת לשבץ את כל הימים הנוספים.",
        "הנחיות טקסט חופשיות והעדפות שלא תורגמו לכלל מובנה אינן מחושבות מחדש בתרחיש.",
    ]


__all__ = ["analyze"]
