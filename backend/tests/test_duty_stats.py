"""מכלול duties in the stats panel (`audit/duty_stats.py` via `shift_stats`)."""

from app.bl.audit import shift_stats

SHIFTS = [{"name": "בוקר", "start_time": "07:00", "end_time": "15:00"}]
EMPLOYEES = [{"name": "דנה"}, {"name": "יוסי"}, {"name": "רון"}]


def _shift(employee, date):
    return {"employee": employee, "shift": "בוקר", "date": date}


def _duty(employee, date, kind="מטבח", weight=1):
    return {"employee": employee, "duty_date": date, "duty_type": kind, "weight": weight}


def _people(stats):
    return {row["employee"]: row for row in stats["by_employee"]}


def test_without_duties_the_figures_are_zero_and_load_is_shifts():
    stats = shift_stats([_shift("דנה", "2026-11-16")], SHIFTS, EMPLOYEES)

    dana = _people(stats)["דנה"]
    assert (dana["duties"], dana["duty_load"], dana["load"]) == (0, 0, 1)
    assert (stats["total_duties"], stats["by_duty"]) == (0, [])


def test_duties_join_the_load_and_order_the_list():
    assignments = [_shift("יוסי", "2026-11-16"), _shift("יוסי", "2026-11-17"),
                   _shift("דנה", "2026-11-18")]
    duties = [_duty("דנה", "2026-11-19"),                          # Thursday
              _duty("דנה", "2026-11-20", kind="שמירה", weight=2),   # Friday
              _duty("רון", "2026-11-21", kind="שמירה", weight=2)]   # Saturday

    stats = shift_stats(assignments, SHIFTS, EMPLOYEES, duties=duties)

    people = _people(stats)
    assert (people["דנה"]["shifts"], people["דנה"]["duties"], people["דנה"]["duty_load"],
            people["דנה"]["weekend_duties"], people["דנה"]["load"]) == (1, 2, 3, 1, 4)
    assert people["רון"]["load"] == 2
    # Heaviest whole load first: דנה 4, יוסי 2 (on more shifts) before רון 2.
    assert [row["employee"] for row in stats["by_employee"]] == ["דנה", "יוסי", "רון"]
    assert (stats["total_duties"], stats["total_duty_load"]) == (3, 5)
    assert stats["by_duty"] == [
        {"duty": "שמירה", "count": 2, "load": 4, "weight": 2},
        {"duty": "מטבח", "count": 1, "load": 1, "weight": 1},
    ]


def test_one_person_sees_only_their_duties():
    duties = [_duty("דנה", "2026-11-19"), _duty("רון", "2026-11-19")]

    stats = shift_stats([], SHIFTS, EMPLOYEES, employee="דנה", duties=duties)

    assert [row["employee"] for row in stats["by_employee"]] == ["דנה"]
    assert stats["total_duties"] == 1
