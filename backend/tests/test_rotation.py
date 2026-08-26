"""The closure cycle: whose weekend it is, computed rather than guessed.

A closure is not another shift to balance. It belongs to one group at a time,
and a scheduler that hands Saturday to whoever is under quota equalises a
number nobody asked to equalise while breaking the cycle the unit planned its
month around. These tests pin the arithmetic that prevents that.

The cases that matter most are the ones where two structures run side by
side: a `round` א and a `triplet` א are not the same א, and a person with no
group at all is not in a rotation.
"""

import datetime

from app.bl import rotation

MORNING = "בוקר"
NIGHT = "לילה"

# A Saturday, so the anchor needs no normalisation to be readable here.
ANCHOR = "2026-08-29"

# Two shifts with declared hours, so the Sunday handover has a clock to read.
# Which of them ends a closure is decided by the earlier start time, never by
# the name (D9).
SHIFTS = [
    {"name": MORNING, "days": [], "start_time": "08:00", "end_time": "16:00",
     "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
    {"name": NIGHT, "days": [], "start_time": "20:00", "end_time": "04:00",
     "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
]


def _profile(employees, shifts=False, **workplace):
    base = {
        "name": "פלוגה", "rotation_mode": "round",
        "first_closure_date": ANCHOR, "first_closure_group": "א",
    }
    base.update(workplace)
    profile = {"workplace": base, "employees": employees}
    if shifts:
        profile["shifts"] = [dict(shift) for shift in SHIFTS]
    return profile


def _saturdays(profile, person, weeks=4):
    rows = rotation.closure_days(
        profile, person,
        datetime.date.fromisoformat(ANCHOR),
        datetime.date.fromisoformat(ANCHOR) + datetime.timedelta(days=7 * weeks - 1),
    )
    return [row["date"] for row in rows if row["is_saturday"]]


def test_round_alternates_and_triplet_turns_every_third_weekend():
    profile = _profile([
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "רון", "exit_pattern": "triplet", "rotation_group": "א"},
    ])

    assert _saturdays(profile, profile["employees"][0]) == [
        "2026-08-29", "2026-09-12",
    ]
    assert _saturdays(profile, profile["employees"][1]) == [
        "2026-08-29", "2026-09-19",
    ]


def test_the_two_cycles_run_side_by_side_and_do_not_share_a_group():
    """A round א and a triplet א are not the same א.

    They coincide on the anchor and separate immediately after. Collapsing
    them into one cycle silently moves somebody's exits, which is the bug
    this separation exists to prevent.
    """
    profile = _profile([
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "רון", "exit_pattern": "triplet", "rotation_group": "א"},
        {"name": "עדי", "exit_pattern": "triplet", "rotation_group": "ג"},
    ])
    third = datetime.date(2026, 9, 12)

    assert rotation.closing_group(profile, third, "round") == "א"
    assert rotation.closing_group(profile, third, "triplet") == "ג"
    # The triplet ג soldier holds the weekend the round א soldier also holds,
    # and the triplet א soldier does not.
    assert "2026-09-12" in _saturdays(profile, profile["employees"][2])
    assert "2026-09-12" not in _saturdays(profile, profile["employees"][1])


def test_round_and_triplet_can_start_from_different_weekends_and_groups():
    """Each structure keeps its own phase even when both staff one shift."""
    profile = _profile([
        {"name": "מפקדת סבב", "exit_pattern": "round", "rotation_group": "א",
         "is_shift_manager": True},
        {"name": "מפקד תלתון", "exit_pattern": "triplet", "rotation_group": "ג",
         "is_shift_manager": True},
    ],
        round_first_closure_date="2026-08-29",
        round_first_closure_group="א",
        triplet_first_closure_date="2026-09-05",
        triplet_first_closure_group="ג",
    )

    first = datetime.date(2026, 8, 29)
    second = datetime.date(2026, 9, 5)
    assert rotation.closing_group(profile, first, "round") == "א"
    assert rotation.closing_group(profile, first, "triplet") == "ב"
    assert rotation.closing_group(profile, second, "round") == "ב"
    assert rotation.closing_group(profile, second, "triplet") == "ג"


def test_a_blank_specific_anchor_does_not_borrow_the_other_cycle():
    profile = _profile([
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "רון", "exit_pattern": "triplet", "rotation_group": "א"},
    ],
        round_first_closure_date=ANCHOR,
        round_first_closure_group="א",
        triplet_first_closure_date="",
        triplet_first_closure_group="א",
    )

    assert rotation.cycle(profile, "round") is not None
    assert rotation.cycle(profile, "triplet") is None


def test_a_group_is_what_makes_a_pattern_rotate():
    """No group means every weekend -- "יוצא כל חמישי לסופ״ש"."""
    weekly = {"name": "טל", "exit_pattern": "hamshushim", "rotation_group": ""}
    rotating = {"name": "אבי", "exit_pattern": "hamshushim", "rotation_group": "א"}
    profile = _profile([weekly, rotating])

    assert _saturdays(profile, weekly) == [
        "2026-08-29", "2026-09-05", "2026-09-12", "2026-09-19",
    ]
    assert _saturdays(profile, rotating) == ["2026-08-29", "2026-09-12"]


def test_the_span_patterns_hold_their_own_run_of_days():
    """חמשושים goes in on Thursday, שושים on Friday, both out Sunday morning.

    The Israeli closure weekend is four dates, not three: the group is
    relieved at the Sunday handover, so the stretch ends there rather than at
    Saturday night. The two patterns differ in when they begin and never in
    when they end.
    """
    profile = _profile([
        {"name": "טל", "exit_pattern": "hamshushim", "rotation_group": ""},
        {"name": "נועה", "exit_pattern": "shushim", "rotation_group": ""},
    ], shifts=True)
    # Monday to Sunday, so exactly one closure falls inside it: the previous
    # weekend's handover is already behind the window.
    week = (datetime.date(2026, 8, 31), datetime.date(2026, 9, 6))

    assert [row["date"] for row in rotation.closure_days(
        profile, profile["employees"][0], *week
    )] == ["2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"]
    assert [row["date"] for row in rotation.closure_days(
        profile, profile["employees"][1], *week
    )] == ["2026-09-04", "2026-09-05", "2026-09-06"]


def test_a_round_weekend_runs_from_thursday_like_any_other_closure():
    """`round` sets *who* closes; the span it sets is the Israeli weekend.

    A cycle naming only its Saturday described a weekend nobody works: the
    group goes in on Thursday and comes off at the Sunday handover, and the
    four dates between are what the rotation is actually about.
    """
    profile = _profile([
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
    ], shifts=True)

    assert [row["date"] for row in rotation.closure_days(
        profile, profile["employees"][0],
        datetime.date(2026, 8, 24), datetime.date(2026, 8, 31),
    )] == ["2026-08-27", "2026-08-28", "2026-08-29", "2026-08-30"]


def test_the_handover_sunday_covers_only_the_first_shift_of_the_day():
    """The last date is a morning, not a day.

    Which shift that is comes off the declared start times rather than off a
    Hebrew name (D9): the earliest shift of the day is the handover, and a
    workplace that declared no times has no clock to read, so its closures
    honestly end on Saturday.
    """
    person = {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"}
    timed = _profile([person], shifts=True)
    untimed = _profile([person])
    untimed["shifts"] = [{"name": MORNING}, {"name": NIGHT}]
    sunday = datetime.date(2026, 8, 30)

    assert rotation.handover_shifts(timed) == [MORNING]
    assert [row["shifts"] for row in rotation.closure_days(
        timed, person, sunday, sunday
    )] == [[MORNING]]
    assert rotation.holds(timed, person, sunday, MORNING) is True
    assert rotation.holds(timed, person, sunday, NIGHT) is False

    assert rotation.handover_shifts(untimed) == []
    assert rotation.closure_days(untimed, person, sunday, sunday) == []


def test_a_weekly_pattern_needs_no_anchor_but_a_rotating_one_does():
    """With no anchor there is no phase, and guessing one moves everybody.

    A person out every weekend has no phase to get wrong, so they are
    unaffected -- refusing them too would remove a real arrangement over a
    field that says nothing about them.
    """
    weekly = {"name": "טל", "exit_pattern": "hamshushim", "rotation_group": ""}
    rotating = {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"}
    profile = {
        "workplace": {"name": "פלוגה", "rotation_mode": "round"},
        "employees": [weekly, rotating],
    }

    assert rotation.cycle(profile) is None
    assert _saturdays(profile, rotating) == []
    assert _saturdays(profile, weekly) == [
        "2026-08-29", "2026-09-05", "2026-09-12", "2026-09-19",
    ]


def test_the_anchor_is_normalised_to_its_own_saturday():
    """A manager naming the Thursday of a חמשוש means that same closure."""
    thursday = _profile([
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
    ], first_closure_date="2026-08-27")

    assert rotation.cycle(thursday)["anchor"] == ANCHOR


def test_weekends_before_the_anchor_count_backwards():
    profile = _profile([
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
    ])

    assert rotation.closing_group(profile, datetime.date(2026, 8, 22), "round") == "ב"
    assert rotation.closing_group(profile, datetime.date(2026, 8, 15), "round") == "א"


def test_the_period_schedule_names_every_cycle_closing_a_weekend():
    profile = _profile([
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "עדי", "exit_pattern": "triplet", "rotation_group": "ג"},
    ])

    rows = rotation.schedule_for_model(
        profile, datetime.date(2026, 9, 12), datetime.date(2026, 9, 12)
    )

    assert rows[0]["weekend"] == "2026-09-12"
    assert rows[0]["closing_groups"] == [
        {"pattern": "round", "group": "א"},
        {"pattern": "triplet", "group": "ג"},
    ]
    assert rows[0]["days"][0]["employees"] == ["דנה", "עדי"]


def test_the_scheduler_blocks_a_person_whose_cycle_is_not_closing():
    """The hard row is what stops the model moving somebody across rotations.

    Only the group actually out of turn is blocked: the closing group stays
    available, and a cycle that is not closing today is untouched.
    """
    from app.bl.scheduler import effective_availability

    profile = _profile([
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "יוסי", "exit_pattern": "round", "rotation_group": "ב"},
        {"name": "אזרח"},
    ])
    profile["shifts"] = [{
        "name": MORNING, "days": [], "start_time": "08:00", "end_time": "16:00",
        "staffing": [{"days": [], "headcount": 1, "required_roles": []}],
    }]

    rows = [
        row for row in effective_availability(profile, [], ANCHOR, ANCHOR)
        if row.get("source") == "closure"
    ]

    # דנה closes this weekend and stays available; the civilian the cycle
    # says nothing about is never constrained.
    assert [row["employee"] for row in rows] == ["יוסי"]
    assert rows[0]["is_hard"] and rows[0]["available"] is False
    assert "סבב א" in rows[0]["reason"]


def test_the_closure_blocks_the_other_group_from_thursday_to_the_handover():
    """The whole stretch, and only the handover on the day it ends.

    Thursday through Saturday belong to the group in, so the other group is
    out on all of them. Sunday is split: they are still out for the morning
    the closure hands over on, and free for the night after it -- blocking
    the whole Sunday would take a day off somebody who is back at work.
    """
    from app.bl.scheduler import effective_availability

    profile = _profile([
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "יוסי", "exit_pattern": "round", "rotation_group": "ב"},
    ], shifts=True)

    blocked = {
        (row["date"], row["shift"])
        for row in effective_availability(
            profile, [], "2026-08-27", "2026-08-30"
        )
        if row.get("source") == "closure"
    }

    # דנה's weekend, so יוסי is the one displaced -- and nobody else is.
    assert all(
        row["employee"] == "יוסי"
        for row in effective_availability(
            profile, [], "2026-08-27", "2026-08-30"
        )
        if row.get("source") == "closure"
    )
    assert blocked == {
        ("2026-08-27", MORNING), ("2026-08-27", NIGHT),
        ("2026-08-28", MORNING), ("2026-08-28", NIGHT),
        ("2026-08-29", MORNING), ("2026-08-29", NIGHT),
        ("2026-08-30", MORNING),
    }


def test_the_audit_stops_at_the_handover_rather_than_the_whole_sunday():
    """Sunday night after a closure is nobody's turn in particular."""
    from app.bl.audit import CROSS_ROTATION, audit

    employees = [
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "יוסי", "exit_pattern": "round", "rotation_group": "ב"},
    ]
    profile = _profile(employees, shifts=True)
    rows = [
        {"employee": "יוסי", "shift": MORNING, "date": "2026-08-30"},
        {"employee": "יוסי", "shift": NIGHT, "date": "2026-08-30"},
    ]

    flagged = [
        warning for warning in audit(rows, SHIFTS, employees, profile=profile)
        if warning["code"] == CROSS_ROTATION
    ]

    assert [warning["shift"] for warning in flagged] == [MORNING]


def test_someone_out_every_weekend_does_not_put_a_rotating_group_out_of_turn():
    """A blank cycle displaces nobody.

    Counting an ungrouped חמשושים person as "the group in" would block the
    group whose turn it genuinely is.
    """
    from app.bl.scheduler import effective_availability

    profile = _profile([
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "טל", "exit_pattern": "hamshushim", "rotation_group": ""},
    ])
    profile["shifts"] = [{
        "name": MORNING, "days": [], "start_time": "08:00", "end_time": "16:00",
        "staffing": [{"days": [], "headcount": 2, "required_roles": []}],
    }]

    rows = [
        row for row in effective_availability(profile, [], ANCHOR, ANCHOR)
        if row.get("source") == "closure"
    ]

    assert rows == []


def test_the_audit_names_a_cross_rotation_assignment():
    """Reported, never blocked -- and kept apart from an ordinary conflict.

    "יוסי has an appointment" is solved by finding somebody else; "יוסי is in
    on סבב א's Saturday" means the rotation drifted, and swapping in another
    name from the wrong group does not fix it.
    """
    from app.bl.audit import CROSS_ROTATION, audit

    employees = [
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "יוסי", "exit_pattern": "round", "rotation_group": "ב"},
        {"name": "רון", "exit_pattern": "triplet", "rotation_group": "א"},
        {"name": "אזרח"},
    ]
    profile = _profile(employees)
    shifts = [{"name": MORNING, "start_time": "08:00", "end_time": "16:00"}]
    rows = [
        {"employee": name, "shift": MORNING, "date": ANCHOR}
        for name in ("דנה", "יוסי", "רון", "אזרח")
    ]

    flagged = [
        warning for warning in audit(rows, shifts, employees, profile=profile)
        if warning["code"] == CROSS_ROTATION
    ]

    # Round א and triplet א both close the anchor weekend, so only round ב is
    # out of turn. The civilian is never named.
    assert [warning["employee"] for warning in flagged] == ["יוסי"]
    assert flagged[0]["details"]["rotation_group"] == "ב"


def test_an_ordinary_weekday_is_nobody_s_closure():
    """Only closure days are constrained.

    Every date maps to some upcoming Saturday, so a check that forgot to ask
    whether the pattern actually spans the day would flag the whole week.
    """
    from app.bl.audit import CROSS_ROTATION, audit

    employees = [
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "יוסי", "exit_pattern": "round", "rotation_group": "ב"},
    ]
    profile = _profile(employees)
    shifts = [{"name": MORNING, "start_time": "08:00", "end_time": "16:00"}]
    tuesday = [
        {"employee": name, "shift": MORNING, "date": "2026-09-01"}
        for name in ("דנה", "יוסי")
    ]

    assert [
        warning for warning in audit(tuesday, shifts, employees, profile=profile)
        if warning["code"] == CROSS_ROTATION
    ] == []


def test_the_audit_is_silent_when_the_cycle_was_never_anchored():
    """No anchor means no phase, so there is nothing to be wrong about."""
    from app.bl.audit import CROSS_ROTATION, audit

    employees = [
        {"name": "דנה", "exit_pattern": "round", "rotation_group": "א"},
        {"name": "יוסי", "exit_pattern": "round", "rotation_group": "ב"},
    ]
    profile = {
        "workplace": {"name": "פלוגה", "rotation_mode": "round"},
        "employees": employees,
    }
    shifts = [{"name": MORNING, "start_time": "08:00", "end_time": "16:00"}]
    rows = [
        {"employee": name, "shift": MORNING, "date": ANCHOR}
        for name in ("דנה", "יוסי")
    ]

    assert [
        warning for warning in audit(rows, shifts, employees, profile=profile)
        if warning["code"] == CROSS_ROTATION
    ] == []
