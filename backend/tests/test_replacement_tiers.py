"""A replacement is searched in stages: role and post first, then wider.

The manager's rule for the changes tab: whoever replaces a soldier is first
a holder of the same role from the shift itself, then the same role from
another place, and only then anyone else who fits. Pure arithmetic, so the
whole contract is fixtures in and an order out.
"""

from app.bl.placement import suggest_alternatives
from app.bl.placement.tiers import OTHER, SAME_POST, SAME_ROLE, Tiers

GATE = "ש.ג"
PATROL = "סיור"
DATE = "2026-08-17"

LEAVING = "דנה"
CREW_MEDIC = "יוסי"
OTHER_MEDIC = "רון"
CREW_DRIVER = "מאיה"
LIGHT_DRIVER = "עומר"


def _profile(**overrides):
    employees = [
        {"name": LEAVING, "role": "חובש"},
        {"name": CREW_MEDIC, "roles": ["חובש"]},
        {"name": OTHER_MEDIC, "role": "חובש"},
        {"name": CREW_DRIVER, "role": "נהג"},
        {"name": LIGHT_DRIVER, "role": "נהג"},
    ]
    shifts = [
        {"name": GATE, "start_time": "07:00", "end_time": "15:00", "days": [],
         "staffing": [{"days": [], "headcount": 2, "required_roles": []}]},
        {"name": PATROL, "start_time": "15:00", "end_time": "23:00", "days": [],
         "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
    ]
    profile = {"workplace": {"name": "בסיס"}, "employees": employees, "shifts": shifts,
               "audit_policy": {"max_weekly_hours": 80.0, "min_rest_hours": 0.0,
                                "max_consecutive_days": 7}}
    return dict(profile, **overrides)


def _slot(shift, date):
    return {"id": "slot-%s-%s" % (shift, date), "shift_name": shift, "slot_date": date,
            "start_time": "07:00" if shift == GATE else "15:00",
            "end_time": "15:00" if shift == GATE else "23:00",
            "headcount": 2 if shift == GATE else 1, "is_on_call": False}


def _row(row_id, employee, shift, date):
    return {"id": row_id, "employee": employee, "shift": shift, "date": date,
            "reason": "בדיקה", "slot_id": "slot-%s-%s" % (shift, date), "source": "manager"}


def _schedule():
    dates = ("2026-08-15", "2026-08-16", DATE)
    rows = [
        _row("a1", LEAVING, GATE, DATE),
        # The gate's own crew this period: a medic and a driver. The other
        # medic stands patrol, so for the gate he is "another place".
        _row("a2", CREW_MEDIC, GATE, "2026-08-15"),
        _row("a3", CREW_DRIVER, GATE, "2026-08-15"),
        _row("a4", CREW_DRIVER, GATE, "2026-08-16"),
        _row("a5", OTHER_MEDIC, PATROL, "2026-08-15"),
        _row("a6", CREW_MEDIC, PATROL, "2026-08-16"),
    ]
    return {"id": "sched-1", "starts_on": dates[0], "ends_on": DATE,
            "slots": [_slot(shift, date) for date in dates for shift in (GATE, PATROL)],
            "assignments": rows}


def _offered(profile=None):
    found = suggest_alternatives(_schedule(), profile or _profile(), LEAVING, GATE, DATE,
                                 moving_assignment_id="a1")
    return found["employees"]


def test_the_same_role_from_the_shift_comes_first_then_from_another_place():
    offered = _offered()
    assert [row["employee"] for row in offered] == [
        CREW_MEDIC, OTHER_MEDIC, LIGHT_DRIVER, CREW_DRIVER,
    ]
    assert [row["tier"] for row in offered] == [SAME_POST, SAME_ROLE, OTHER, OTHER]
    assert offered[0]["tier_label"] == "אותו תפקיד מהמשמרת"
    assert offered[1]["tier_label"] == "אותו תפקיד ממקום אחר"


def test_a_stage_outranks_a_lighter_week():
    """The crew medic carries more than the patrol medic and still comes
    first: the stage is asked before the load is."""
    offered = _offered()
    hours = {row["employee"]: row["hours"] for row in offered}
    assert hours[CREW_MEDIC] > hours[OTHER_MEDIC]
    assert offered[0]["employee"] == CREW_MEDIC


def test_listing_the_shift_makes_someone_part_of_its_crew():
    profile = _profile()
    profile["employees"] = [
        dict(row, eligible_shifts=[GATE, PATROL]) if row["name"] == OTHER_MEDIC else row
        for row in profile["employees"]
    ]
    tiers = Tiers(_schedule(), profile, LEAVING, GATE)
    assert tiers.tier(OTHER_MEDIC) == SAME_POST


def test_one_purpose_is_one_place_at_different_hours():
    profile = _profile()
    profile["shifts"] = [dict(row, purpose="עמדה") for row in profile["shifts"]]
    tiers = Tiers(_schedule(), profile, LEAVING, GATE)
    assert tiers.tier(OTHER_MEDIC) == SAME_POST


def test_with_no_role_to_match_the_stages_are_the_post_alone():
    profile = _profile()
    profile["employees"] = [
        {"name": row["name"]} if row["name"] == LEAVING else row
        for row in profile["employees"]
    ]
    tiers = Tiers(_schedule(), profile, LEAVING, GATE)
    assert tiers.tier(CREW_DRIVER) == SAME_POST
    assert tiers.tier(LIGHT_DRIVER) == SAME_ROLE
    assert tiers.label(SAME_ROLE) == "ממקום אחר"


def test_the_absence_pick_is_the_earliest_stage_not_the_lightest_person():
    """The changes tab's fair pick: the crew medic, though the patrol medic
    and the drivers carry fewer shifts."""
    from app.bl.absence.options import _Fill

    schedule, profile = _schedule(), _profile()
    leaving = schedule["assignments"][0]
    fill = _Fill(profile, schedule, [], [], [dict(
        action="remove", employee=LEAVING, date=DATE, shift=GATE, reason="חולה")])
    slot = fill.slot(leaving, schedule, _offered(profile), "")
    assert slot["pick"] == CREW_MEDIC
    assert [row["employee"] for row in slot["candidates"]][:2] == [CREW_MEDIC, OTHER_MEDIC]
