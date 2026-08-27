"""Shifts that are not one person: four, ten, a shadow, a shift for nobody.

The arithmetic under a multi-person shift is answered by four different
modules — `audit.py` warns, `shift_stats` draws the chart, `tools.py` lists
the gaps, `simulate.py` says what a change would do — and the manager reads
all four on one screen. So the property these tests exist for is not that any
one of them is right in isolation but that **they agree**: a cell the warning
calls short must not be a cell the coverage bar calls full, and a seat the
gap list offers must be a seat the audit says is empty.

Two edge cases break that agreement in opposite directions, and both are real
in the source files this product was built from:

- **A headcount that changes across the week.** `staffing` is a list of
  per-day groups, so a patrol running with four on weekdays and ten on Friday
  is one shift with two groups. Which number applies on 2026-08-21 is
  arithmetic, and the grid the schedule was *generated* into already did it.
- **A shadow shift.** Someone learning the shift stands on it, appears on the
  board, accrues the hours, and does not fill one of the seats it asked for.
  A count of bodies gets that backwards, and reports a slot covered by the
  person who is there precisely because they cannot yet cover it.
"""

from app.bl.audit import (
    OVERSTAFFED,
    UNFILLED,
    audit,
    counts_toward_staffing,
    required_headcount,
    shift_stats,
)
from app.bl.scheduler import build_slots
from app.bl.simulate import _coverage

# This workplace's own vocabulary (D9). `חפיפה` is a shift, not a keyword —
# nothing in the code matches on the name, and these tests would pass with it
# renamed.
PATROL = "סיור"
OVERLAP = "חפיפה"

# Four every day, ten on Friday. The Friday group is written WITHOUT the
# `יום ` prefix, because the interview collects both forms and `build_slots`
# has always read them as the same day.
SHIFTS = [
    {
        "name": PATROL, "start_time": "07:00", "end_time": "15:00",
        "days": [], "hour_weight": 1.0,
        "staffing": [
            {"days": [], "headcount": 4, "required_roles": []},
            {"days": ["שישי"], "headcount": 10, "required_roles": []},
        ],
    },
    {
        "name": OVERLAP, "start_time": "15:00", "end_time": "17:00",
        "days": [], "shift_type": "overlap", "hour_weight": 1.0,
        "staffing": [{"days": [], "headcount": 2, "required_roles": []}],
    },
]

TEAM = ["ע%d" % index for index in range(1, 11)]
TRAINEE = "חניך"
EMPLOYEES = [{"name": name, "role": "לוחם"} for name in TEAM] + [
    {"name": TRAINEE, "role": "לוחם", "is_trainee": True,
     "counts_toward_staffing": False},
]

PROFILE = {
    "workplace": {"name": "יחידה"},
    "shifts": SHIFTS,
    "employees": EMPLOYEES,
    "training_policy": {"counts_toward_staffing": False},
}

MONDAY = "2026-08-17"
FRIDAY = "2026-08-21"


def _assign(employee, shift, date):
    return {"employee": employee, "shift": shift, "date": date}


def _by_code(warnings, code):
    return [warning for warning in warnings if warning["code"] == code]


def _staff(shift, date, count, extra=()):
    return [_assign(name, shift, date) for name in TEAM[:count]] + [
        _assign(name, shift, date) for name in extra
    ]


# --- a headcount that changes across the week -------------------------------

def test_friday_asks_for_ten_where_the_rest_of_the_week_asks_for_four():
    monday = build_slots(PROFILE, MONDAY, MONDAY)
    friday = build_slots(PROFILE, FRIDAY, FRIDAY)

    assert [slot["headcount"] for slot in monday if
            slot["shift_name"] == PATROL] == [4]
    assert [slot["headcount"] for slot in friday if
            slot["shift_name"] == PATROL] == [10]


def test_the_audit_asks_for_the_same_ten_the_grid_was_built_from():
    """The bug this pins: a Friday generated to ten, audited against four.

    `build_slots` normalises the `יום ` prefix and the audit did not, so the
    per-day group was skipped and the weekday default applied. Every Friday
    the agent built to its own contract came back reported overstaffed the
    moment it was saved.
    """
    slots = build_slots(PROFILE, FRIDAY, FRIDAY)
    warnings = audit(
        _staff(PATROL, FRIDAY, 10), SHIFTS, EMPLOYEES,
        profile=PROFILE, slots=slots,
    )

    assert _by_code(warnings, OVERSTAFFED) == []
    assert _by_code(warnings, UNFILLED) == [
        warning for warning in warnings
        if warning["code"] == UNFILLED and warning["shift"] == OVERLAP
    ]


def test_an_unprefixed_weekday_names_the_same_day_as_a_prefixed_one():
    prefixed = dict(SHIFTS[0], staffing=[
        {"days": [], "headcount": 4, "required_roles": []},
        {"days": ["יום שישי"], "headcount": 10, "required_roles": []},
    ])
    import datetime

    friday = datetime.date.fromisoformat(FRIDAY)
    assert required_headcount([SHIFTS[0]], PATROL, friday) == 10
    assert required_headcount([prefixed], PATROL, friday) == 10


def test_the_stored_grid_outranks_the_current_profile():
    """An imported week keeps the staffing the file actually ran with.

    `commit_import` builds the grid from the sheet's own rows rather than
    from today's vocabulary (D9), and a profile edited since must not
    retroactively decide that last month's six-person Tuesday was short.
    """
    import datetime

    slots = [{"shift_name": PATROL, "slot_date": MONDAY, "headcount": 6}]
    monday = datetime.date.fromisoformat(MONDAY)

    assert required_headcount(SHIFTS, PATROL, monday) == 4
    assert required_headcount(SHIFTS, PATROL, monday, slots) == 6


def test_a_slot_asking_for_nobody_is_neither_short_nor_overstaffed():
    profile = dict(PROFILE, shifts=[dict(SHIFTS[0], staffing=[
        {"days": [], "headcount": 0, "required_roles": []},
    ])])
    slots = build_slots(profile, MONDAY, MONDAY)

    warnings = audit(
        [], profile["shifts"], EMPLOYEES, profile=profile, slots=slots
    )
    assert _by_code(warnings, UNFILLED) == []
    assert _by_code(warnings, OVERSTAFFED) == []


def test_a_headcount_nobody_stated_is_not_assumed_to_be_one():
    """Silence is not a requirement of one, and an invented denominator is
    what makes a coverage percentage fiction."""
    shifts = [{"name": PATROL, "start_time": "07:00", "end_time": "15:00"}]
    warnings = audit([_assign(TEAM[0], PATROL, MONDAY)], shifts, EMPLOYEES)

    assert _by_code(warnings, UNFILLED) == []
    assert _by_code(warnings, OVERSTAFFED) == []


# --- the shadow shift -------------------------------------------------------

def test_a_trainee_on_a_shadow_shift_leaves_the_seat_needing_filling():
    slots = build_slots(PROFILE, MONDAY, MONDAY)
    warnings = audit(
        _staff(PATROL, MONDAY, 3, extra=[TRAINEE]),
        SHIFTS, EMPLOYEES, profile=PROFILE, slots=slots,
    )
    short = _by_code(warnings, UNFILLED)

    patrol = [row for row in short if row["shift"] == PATROL]
    assert len(patrol) == 1
    assert patrol[0]["details"] == {"assigned": 3, "required": 4}


def test_a_trainee_beside_a_full_slot_does_not_overstaff_it():
    """The shadow shift working: four on the patrol, one learning it."""
    slots = build_slots(PROFILE, MONDAY, MONDAY)
    warnings = audit(
        _staff(PATROL, MONDAY, 4, extra=[TRAINEE]),
        SHIFTS, EMPLOYEES, profile=PROFILE, slots=slots,
    )

    assert _by_code(warnings, OVERSTAFFED) == []
    assert [row for row in _by_code(warnings, UNFILLED)
            if row["shift"] == PATROL] == []


def test_the_manager_may_say_a_trainee_does_count():
    """The explicit field wins over the trainee flag, in both directions."""
    counted = {"name": TRAINEE, "is_trainee": True,
               "counts_toward_staffing": True}
    held_back = {"name": TEAM[0], "counts_toward_staffing": False}

    assert counts_toward_staffing(counted, PROFILE) is True
    assert counts_toward_staffing(held_back, PROFILE) is False


def test_a_workplace_policy_settles_the_trainees_nobody_ruled_on():
    person = {"name": TRAINEE, "is_trainee": True}

    assert counts_toward_staffing(person, PROFILE) is False
    assert counts_toward_staffing(
        person, {"training_policy": {"counts_toward_staffing": True}}
    ) is True


def test_someone_the_roster_never_heard_of_still_fills_a_seat():
    """A schedule outlives the roster it was built against."""
    assert counts_toward_staffing(None, PROFILE) is True
    assert counts_toward_staffing({}, PROFILE) is True


# --- the four readers agreeing ---------------------------------------------

def test_the_coverage_chart_agrees_with_the_warning_printed_under_it():
    """The property `shift_stats` says outright is worth more than the rest.

    Three of the four seats filled and a trainee shadowing the fourth: the
    audit calls it three of four, and a chart that called the same cell full
    because five bodies were on it would be worse than drawing no chart.
    """
    slots = build_slots(PROFILE, MONDAY, MONDAY)
    rows = _staff(PATROL, MONDAY, 3, extra=[TRAINEE])

    warnings = audit(
        rows, SHIFTS, EMPLOYEES, profile=PROFILE, slots=slots
    )
    stats = shift_stats(
        rows, SHIFTS, EMPLOYEES, slots=slots, profile=PROFILE
    )

    patrol = [row for row in _by_code(warnings, UNFILLED)
              if row["shift"] == PATROL][0]
    # 4 patrol seats + 2 overlap seats, with 3 patrol seats filled.
    assert stats["coverage"]["required"] == 6
    assert stats["coverage"]["assigned"] == patrol["details"]["assigned"]
    assert stats["coverage"]["unfilled_slots"] == len(
        _by_code(warnings, UNFILLED)
    )


def test_coverage_counts_ten_seats_on_a_friday_not_four():
    slots = build_slots(PROFILE, FRIDAY, FRIDAY)
    stats = shift_stats(
        _staff(PATROL, FRIDAY, 10), SHIFTS, EMPLOYEES,
        slots=slots, profile=PROFILE,
    )

    # Ten on the patrol, two on the overlap nobody is on.
    assert stats["coverage"]["required"] == 12
    assert stats["coverage"]["assigned"] == 10


def test_a_simulation_does_not_promise_a_gap_a_trainee_closed():
    slots = build_slots(PROFILE, MONDAY, MONDAY)
    before = _staff(PATROL, MONDAY, 3)
    after = before + [_assign(TRAINEE, PATROL, MONDAY)]

    moved = _coverage(before, after, slots, EMPLOYEES, PROFILE)
    assert moved["delta"] == 0

    real = _coverage(
        before, before + [_assign(TEAM[3], PATROL, MONDAY)],
        slots, EMPLOYEES, PROFILE,
    )
    assert real["delta"] == 1


def test_an_overstaffed_slot_does_not_lend_its_spare_body_to_an_empty_one():
    """Capped per slot: eight on the patrol does not cover the overlap."""
    slots = build_slots(PROFILE, MONDAY, MONDAY)
    rows = _staff(PATROL, MONDAY, 8)

    stats = shift_stats(
        rows, SHIFTS, EMPLOYEES, slots=slots, profile=PROFILE
    )
    assert stats["coverage"]["assigned"] == 4
    assert stats["coverage"]["required"] == 6
