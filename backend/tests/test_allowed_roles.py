"""A shift can be limited to the roles qualified to stand it."""

from app.bl.placement.values import is_eligible
from app.bl.profile_service.shifts import shifts as validate_shifts
from app.bl.scheduler.directives import translated_row
from app.bl.shared import role_qualified
from app.bl.solver import generate_day


SHIFT = "חמ״ל"


def _profile(allowed):
    return {
        "workplace": {"name": "יחידה"},
        "employees": [
            {"name": "דנה", "role": "קצינה"},
            {"name": "יוסי", "role": "לוחם"},
            {"name": "רון", "role": "לוחם", "roles": ["קצין"]},
        ],
        "shifts": [{
            "name": SHIFT, "start_time": "07:00", "end_time": "15:00", "days": [],
            "allowed_roles": allowed,
            "staffing": [{"days": [], "headcount": 3, "required_roles": []}],
        }],
    }


def test_an_empty_list_restricts_nobody():
    assert role_qualified({"role": "לוחם"}, {"allowed_roles": []})
    assert role_qualified({}, None)


def test_any_held_role_qualifies():
    shift = {"allowed_roles": ["קצין"]}
    assert role_qualified({"role": "לוחם", "roles": ["קצין"]}, shift)
    assert not role_qualified({"role": "לוחם"}, shift)
    assert not role_qualified({}, shift)


def test_the_solver_places_only_qualified_roles():
    result = generate_day(_profile(["קצינה", "קצין"]), "2026-09-01")

    assert sorted(row["employee"] for row in result["assignments"]) == ["דנה", "רון"]


def test_the_solver_places_everyone_when_the_shift_names_no_role():
    result = generate_day(_profile([]), "2026-09-01")

    assert len(result["assignments"]) == 3


def test_placement_reports_an_unqualified_role():
    profile = _profile(["קצינה"])
    assert is_eligible(profile, "דנה", SHIFT)
    assert not is_eligible(profile, "יוסי", SHIFT)


def test_a_translated_pin_on_an_unqualified_role_is_refused():
    profile = _profile(["קצינה"])
    people = {row["name"]: row for row in profile["employees"]}
    definitions = {SHIFT: profile["shifts"][0]}
    row = {"source_id": "s1", "action": "required_assignment", "employee": "יוסי",
           "date": "2026-09-01", "shift": SHIFT, "reason": "ביקש"}
    slots = {(SHIFT, "2026-09-01")}

    assert translated_row(row, {"s1"}, people, slots, definitions=definitions) is None
    assert translated_row(dict(row, employee="דנה"), {"s1"}, people, slots,
                          definitions=definitions) is not None


def test_setup_stores_the_list_trimmed_and_unique():
    [shift] = validate_shifts([{"name": SHIFT, "allowed_roles": [" קצין ", "קצין", ""]}])

    assert shift["allowed_roles"] == ["קצין"]
