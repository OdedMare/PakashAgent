"""A broken soft wish says what honouring it would have cost (`solver/wishes.py`)."""

from app.bl.solver import generate_span, wishes
from app.bl.solver.model import Model
from app.bl.solver.problem import Problem, slots_for

MORNING = "בוקר"
DAY = "2026-09-01"


def _profile(names, headcount=1):
    return {"workplace": {"name": "יחידה"}, "employees": [{"name": name} for name in names],
            "shifts": [{"name": MORNING, "start_time": "07:00", "end_time": "15:00", "days": [],
                        "staffing": [{"days": [], "headcount": headcount, "required_roles": []}]}]}


def _avoid(name, weight=1.0, reason="מעדיף/ה לא"):
    return {"kind": "avoid", "employees": [name], "shifts": [MORNING], "weight": weight,
            "reason": reason}


def _wish_notes(result):
    return [note for note in result["notes"] if "בקשה רכה" in note]


def test_a_wish_that_would_empty_a_seat_says_which():
    result = generate_span(_profile(["אבי"]), DAY, DAY, requests=[_avoid("אבי")],
                           time_limit=1.0, workers=2)

    notes = _wish_notes(result)
    assert len(notes) == 1
    assert notes[0].endswith("כיבודה היה משאיר בחוסר את בוקר בתאריך %s." % DAY)


def test_a_wish_that_would_break_another_says_whose():
    requests = [_avoid("אבי", reason="לימודים"), _avoid("בני", weight=2.0, reason="טיפול רפואי")]
    result = generate_span(_profile(["אבי", "בני"]), DAY, DAY, requests=requests,
                           time_limit=1.0, workers=2)

    notes = _wish_notes(result)
    assert len(notes) == 1 and notes[0].startswith("אבי שובץ/ה")
    assert "כיבודה היה שובר בקשה רכה אחרת: בני שובץ/ה בבוקר" in notes[0]
    assert "טיפול רפואי" in notes[0]


def test_only_the_costliest_wishes_are_probed():
    days = ["2026-09-0%d" % day for day in range(1, 6)]
    profile = _profile(["אבי"])
    requests = [dict(_avoid("אבי", weight=1.0 + index), dates=[day], reason="יום %d" % index)
                for index, day in enumerate(days)]

    result = generate_span(profile, days[0], days[-1], requests=requests, time_limit=1.0, workers=2)

    notes = _wish_notes(result)
    assert len(notes) == len(days)
    explained = [note for note in notes if "כיבודה" in note]
    assert len(explained) == wishes.PROBES
    assert all("יום 0" not in note and "יום 1" not in note for note in explained)


def test_no_snapshot_is_taken_without_a_soft_wish():
    profile = _profile(["אבי"])
    model = Model(Problem(profile, slots_for(profile, DAY, DAY)))

    assert wishes.snapshot(model) is None
