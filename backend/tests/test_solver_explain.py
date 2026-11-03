"""An empty seat says who could not take it and why (`solver/explain.py`)."""

from app.bl.solver import generate_span
from app.bl.solver.problem import Problem, slots_for

MORNING, EVENING = "בוקר", "ערב"
DAY = "2026-09-01"


def _shift(name, start, end, headcount=1, roles=None, manager=False):
    return {"name": name, "start_time": start, "end_time": end, "days": [],
            "requires_shift_manager": manager,
            "staffing": [{"days": [], "headcount": headcount, "required_roles": roles or []}]}


def _profile(people, shifts=None):
    return {"workplace": {"name": "יחידה"}, "employees": people,
            "shifts": shifts or [_shift(MORNING, "07:00", "15:00", headcount=2)]}


def _solve(profile, **options):
    return generate_span(profile, DAY, DAY, time_limit=1.0, workers=2, **options)


def _short(result):
    return [note for note in result["notes"] if "נשארה בחוסר" in note]


def test_an_empty_seat_names_who_was_away_and_why():
    profile = _profile([{"name": "אבי"}, {"name": "בני"}, {"name": "גדי", "eligible_shifts": [EVENING]}],
                       [_shift(MORNING, "07:00", "15:00", headcount=3),
                        _shift(EVENING, "15:00", "23:00", headcount=0)])
    absent = [{"employee": "בני", "date": DAY, "available": False, "is_hard": True}]

    notes = _short(_solve(profile, availability=absent))

    assert len(notes) == 1
    assert "בחוסר של 2" in notes[0] and "מתוך 3" in notes[0]
    assert "1 לא זמינים (אילוץ או היעדרות) (בני)" in notes[0]
    assert "1 לא כשירים למשמרת (גדי)" in notes[0]


def test_the_rotation_and_a_duty_are_told_apart_from_an_absence():
    profile = _profile([{"name": "אבי"}, {"name": "בני"}, {"name": "גדי"}],
                       [_shift(MORNING, "07:00", "15:00", headcount=3)])
    blocked = [
        {"employee": "בני", "date": DAY, "available": False, "is_hard": True, "source": "rotation"},
        {"employee": "גדי", "date": DAY, "available": False, "is_hard": True,
         "constraint_type": "duty"},
    ]

    note = _short(_solve(profile, availability=blocked))[0]

    assert "בבית לפי הסבב (בני)" in note
    assert "בתורנות או במשימה (גדי)" in note


def test_a_seat_the_rest_rule_empties_says_so():
    profile = _profile([{"name": "אבי"}], [_shift(MORNING, "07:00", "15:00"),
                                           _shift(EVENING, "15:00", "23:00")])

    notes = _short(_solve(profile))

    assert len(notes) == 1
    assert any(word in notes[0] for word in ("משובצים במשמרת חופפת", "בלי מנוחה מספקת"))
    assert "(אבי)" in notes[0]


def test_a_missing_role_is_a_note_too():
    profile = _profile([{"name": "אבי", "roles": ["חובש"]}, {"name": "בני"}],
                       [_shift(MORNING, "07:00", "15:00", roles=["חובש"])])
    absent = [{"employee": "אבי", "date": DAY, "available": False, "is_hard": True}]

    notes = _solve(profile, availability=absent)["notes"]

    assert any(note.startswith("חסר/ה חובש בבוקר בתאריך %s." % DAY)
               and "מתוך 1: 1 לא זמינים" in note and "(אבי)" in note for note in notes)


def test_a_role_nobody_holds_is_named_as_such():
    profile = _profile([{"name": "אבי"}], [_shift(MORNING, "07:00", "15:00", roles=["נהג"])])

    notes = _solve(profile)["notes"]

    assert any("אין בצוות אף אחד/ת בתפקיד נהג" in note for note in notes)


def test_a_missing_shift_manager_is_a_note():
    profile = _profile([{"name": "אבי"}], [_shift(MORNING, "07:00", "15:00", manager=True)])

    notes = _solve(profile)["notes"]

    assert any(note.startswith("אין מפקד/ת משמרת בבוקר") and "אין בצוות אף אחד/ת שמוגדר/ת" in note
               for note in notes)


def test_a_filled_schedule_carries_no_coverage_note():
    profile = _profile([{"name": "אבי"}, {"name": "בני"}])

    assert _solve(profile)["notes"] == []


def test_refusal_names_the_test_legality_runs():
    profile = _profile([{"name": "אבי"}, {"name": "בני", "eligible_shifts": [EVENING]}],
                       [_shift(MORNING, "07:00", "15:00"), _shift(EVENING, "15:00", "23:00")])
    problem = Problem(profile, slots_for(profile, DAY, DAY),
                      requests=[{"kind": "avoid", "employees": ["אבי"], "is_hard": True,
                                 "shifts": [EVENING]}])
    morning, evening = (problem.keys[(name, DAY)] for name in (MORNING, EVENING))

    assert problem.refusal("אבי", morning) == ""
    assert problem.refusal("אבי", evening) == "avoid"
    assert problem.refusal("בני", morning) == "ineligible"
    assert ("אבי", morning) in problem.legal and ("אבי", evening) not in problem.legal
