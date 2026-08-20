"""What `bl/placement.py` says about a placement before it is made.

Table-driven like `test_audit.py`, and for the same reason: this module is
pure arithmetic, so its whole contract is expressible as fixtures in and
sentences out. There is no model anywhere in this file — which is the
property being tested as much as any individual case.

Three things here are the point of the feature and are asserted directly:

- **It never blocks.** Every result carries `blocking: False`, whatever it
  found (D3).
- **It reports only what the placement causes.** A schedule already carrying
  a warning does not attribute it to an unrelated drag.
- **The alternatives are real.** Everything offered is re-checked, so an
  option that would warn is never offered as a way out of a warning.
"""

import pytest

from app.bl.placement import check, suggest_alternatives

MORNING = "בוקר"
EVENING = "צהריים"
NIGHT = "כונן לילה"

DANA = "דנה"
YOSSI = "יוסי"
RON = "רון"

PROFILE = {
    "workplace": {"name": "מוקד"},
    "employees": [
        {"name": DANA, "eligible_shifts": [MORNING]},
        {"name": YOSSI, "eligible_shifts": [MORNING, EVENING]},
        {"name": RON, "eligible_shifts": [MORNING, EVENING]},
    ],
    "shifts": [
        {
            "name": MORNING, "start_time": "07:00", "end_time": "15:00",
            "days": [], "is_on_call": False, "hour_weight": 1.0,
            "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
        },
        {
            "name": EVENING, "start_time": "15:00", "end_time": "23:00",
            "days": [], "is_on_call": False, "hour_weight": 1.0,
            "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
        },
    ],
    "audit_policy": {
        "max_weekly_hours": 45.0,
        "max_consecutive_days": 6,
        "min_rest_hours": 8.0,
    },
}


def _slot(shift, date, headcount=1):
    return {
        "id": "slot-%s-%s" % (shift, date),
        "shift_name": shift,
        "slot_date": date,
        "start_time": "07:00" if shift == MORNING else "15:00",
        "end_time": "15:00" if shift == MORNING else "23:00",
        "headcount": headcount,
        "is_on_call": False,
    }


def _assignment(row_id, employee, shift, date):
    return {
        "id": row_id,
        "employee": employee,
        "shift": shift,
        "date": date,
        "reason": "בדיקה",
        "slot_id": "slot-%s-%s" % (shift, date),
        "source": "manager",
    }


def _profile_wanting(shift, headcount):
    """The same profile with one shift asking for more people.

    The required headcount is read off the **profile's** `staffing`, not off
    the stored slot -- `audit._headcount_for` is where that is decided. A
    fixture that changed only the slot would leave the requirement at one and
    the test would be measuring nothing.
    """
    shifts = []
    for row in PROFILE["shifts"]:
        if row["name"] == shift:
            row = dict(row, staffing=[
                {"days": [], "headcount": headcount, "required_roles": []},
            ])
        shifts.append(row)
    return dict(PROFILE, shifts=shifts)


def _schedule(
    assignments=(),
    dates=("2026-08-16", "2026-08-17", "2026-08-18"),
    evening_headcount=1,
):
    """A week of morning and evening slots, staffed by whoever is passed."""
    slots = []
    for date in dates:
        slots.append(_slot(MORNING, date))
        slots.append(_slot(EVENING, date, headcount=evening_headcount))
    return {
        "id": "sched-1",
        "starts_on": dates[0],
        "ends_on": dates[-1],
        "status": "draft",
        "slots": slots,
        "assignments": list(assignments),
        "warnings": [],
    }


# -- the clean case --------------------------------------------------------


def test_a_free_slot_and_a_qualified_person_is_ok():
    result = check(_schedule(), PROFILE, YOSSI, MORNING, "2026-08-17")
    assert result["ok"] is True
    assert result["reasons"] == []
    assert result["eligible"] is True
    # Nothing to offer when nothing is wrong: a list of alternatives beside a
    # clean result would read as a suggestion to reconsider.
    assert result["alternatives"] == {"employees": [], "slots": []}


def test_nothing_ever_blocks():
    """Whatever it finds, it advises (D3).

    Run against the worst placement the fixtures can produce — an ineligible
    person, double-booked, against a constraint — because if anything were
    ever going to gate, it would be this.
    """
    schedule = _schedule([_assignment("a1", DANA, MORNING, "2026-08-17")])
    result = check(
        schedule, PROFILE, DANA, MORNING, "2026-08-17",
        availability=[{
            "employee": DANA, "date": "2026-08-17", "shift": "",
            "available": False, "reason": "חופשה",
        }],
    )
    assert result["ok"] is False
    assert result["blocking"] is False


# -- what it catches -------------------------------------------------------


def test_double_booking_is_reported():
    schedule = _schedule([_assignment("a1", YOSSI, MORNING, "2026-08-17")])
    result = check(schedule, PROFILE, YOSSI, MORNING, "2026-08-17")
    assert result["ok"] is False
    assert any(row["code"] == "double_booked" for row in result["warnings"])


def test_a_recorded_constraint_is_reported():
    result = check(
        _schedule(), PROFILE, YOSSI, MORNING, "2026-08-17",
        availability=[{
            "employee": YOSSI, "date": "2026-08-17", "shift": "",
            "available": False, "reason": "לימודים",
        }],
    )
    assert result["ok"] is False
    assert any(row["code"] == "unavailable" for row in result["warnings"])
    # The manager's own recorded reason travels with it, because "why not"
    # is the question the dialog exists to answer.
    assert any("לימודים" in text for text in result["reasons"])


def test_an_ineligible_shift_is_reported_first():
    """Eligibility is not an audit warning, and is reported anyway.

    `audit.py` audits what a schedule *is*; whether the roster says this
    person works this shift is a fact about the roster. It belongs in the
    same list because to the manager it is the same kind of information.
    """
    result = check(_schedule(), PROFILE, DANA, EVENING, "2026-08-17")
    assert result["ok"] is False
    assert result["eligible"] is False
    assert DANA in result["reasons"][0] and EVENING in result["reasons"][0]


def test_an_unrestricted_employee_is_eligible_everywhere():
    """A roster that names no eligible shifts is saying nothing, not no."""
    profile = dict(PROFILE, employees=[{"name": DANA}])
    result = check(_schedule(), profile, DANA, EVENING, "2026-08-17")
    assert result["eligible"] is True


# -- what it does *not* report ---------------------------------------------


def test_a_standing_warning_is_not_blamed_on_this_placement():
    """The board's existing gaps are not the drag's fault.

    An unstaffed Tuesday evening is true before and after placing somebody
    on Monday morning. Attributing it to the drag would teach the manager to
    ignore the dialog, which costs the feature entirely.
    """
    schedule = _schedule()
    result = check(schedule, PROFILE, YOSSI, MORNING, "2026-08-16")
    unfilled = [row for row in result["warnings"] if row["code"] == "unfilled"]
    # Every other slot in the fixture is unstaffed, and none of them is this
    # placement's doing.
    assert unfilled == []
    assert result["ok"] is True


def test_the_moved_row_leaves_before_the_new_one_arrives():
    """A move is checked as a move, not as one person in two places.

    Without dropping the row being dragged, every drag of an assignment onto
    a different slot would report the double-booking it is in the middle of
    resolving.
    """
    schedule = _schedule([_assignment("a1", YOSSI, MORNING, "2026-08-17")])
    result = check(
        schedule, PROFILE, YOSSI, EVENING, "2026-08-17",
        moving_assignment_id="a1",
    )
    assert result["ok"] is True


def test_over_hours_already_true_is_not_re_reported():
    """`_over_hours` writes the running total into its sentence.

    Keyed on the message, a placement pushing somebody from 48 to 56 hours
    would read as a brand-new warning. The identity is code+person+date+shift
    for exactly this case.
    """
    dates = ["2026-08-%02d" % day for day in range(16, 23)]
    rows = [
        _assignment("m%d" % n, RON, MORNING, date)
        for n, date in enumerate(dates)
    ]
    schedule = _schedule(rows, dates=tuple(dates))
    result = check(schedule, PROFILE, RON, EVENING, dates[0])
    over = [row for row in result["warnings"] if row["code"] == "over_hours"]
    assert over == []


# -- the alternatives ------------------------------------------------------


def test_alternatives_offer_qualified_free_colleagues():
    schedule = _schedule()
    found = suggest_alternatives(
        schedule, PROFILE, DANA, EVENING, "2026-08-17",
    )
    names = [row["employee"] for row in found["employees"]]
    # דנה is not offered as her own alternative; both evening-qualified
    # colleagues are.
    assert DANA not in names
    assert set(names) == {YOSSI, RON}


def test_alternatives_never_offer_somebody_who_would_warn():
    """An option that warns is not an alternative.

    The evening wants two people and יוסי holds one of the seats, so there
    is genuinely room for a second. He is still not offered — placing him
    twice would hand the manager a double-booking as the fix for a
    constraint — while רון, who fits cleanly, is.
    """
    profile = _profile_wanting(EVENING, 2)
    schedule = _schedule(
        [_assignment("a1", YOSSI, EVENING, "2026-08-17")], evening_headcount=2,
    )
    found = suggest_alternatives(
        schedule, profile, DANA, EVENING, "2026-08-17",
    )
    assert [row["employee"] for row in found["employees"]] == [RON]


def test_alternatives_offer_the_lightest_week_first():
    """The same fairness arithmetic `audit.fairness()` reports, applied to a
    choice: the person carrying least is offered first."""
    schedule = _schedule([
        _assignment("a1", YOSSI, MORNING, "2026-08-16"),
        _assignment("a2", YOSSI, MORNING, "2026-08-18"),
    ])
    found = suggest_alternatives(
        schedule, PROFILE, DANA, EVENING, "2026-08-17",
    )
    assert [row["employee"] for row in found["employees"]] == [RON, YOSSI]


def test_alternatives_offer_nearby_slots_for_the_same_person():
    schedule = _schedule([_assignment("a1", RON, MORNING, "2026-08-17")])
    found = suggest_alternatives(
        schedule, PROFILE, RON, MORNING, "2026-08-17",
        moving_assignment_id="a1",
    )
    dates = [row["slot_date"] for row in found["slots"]]
    assert dates, "a week with empty slots should offer somewhere to go"
    # Ordered by distance from the date the manager actually wanted.
    distances = [row["distance"] for row in found["slots"]]
    assert distances == sorted(distances)


def test_a_warning_carries_its_alternatives():
    """The two halves arrive together: a manager told why and left there has
    to go find the replacement by reading the grid."""
    result = check(
        _schedule(), PROFILE, DANA, EVENING, "2026-08-17",
    )
    assert result["ok"] is False
    assert result["alternatives"]["employees"], "a reason without a way out"


# -- Hebrew is data (D9/FILE_FORMATS) --------------------------------------


@pytest.mark.parametrize("shift", [MORNING, EVENING, NIGHT])
def test_shift_names_come_from_the_profile(shift):
    """Nothing here matches a name against a hardcoded list.

    `כונן לילה` is not in this profile's vocabulary at all, and a placement
    naming it is still checked rather than rejected — the shift contributes
    no hours, exactly as `audit._row` documents.
    """
    result = check(_schedule(), PROFILE, YOSSI, shift, "2026-08-17")
    assert result["blocking"] is False
