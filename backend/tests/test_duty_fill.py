"""The fair fill (`complex_duties/fill.py`) and the balance, pure."""

import datetime

from app.bl.complex_duties.balance import balance
from app.bl.complex_duties.fill import suggest

D = datetime.date
MON, TUE, FRI = D(2026, 11, 16), D(2026, 11, 17), D(2026, 11, 20)
KITCHEN = {"id": "k", "name": "מטבח", "seats": 1, "days": [], "weight": 1, "active": True}


def _soldier(name, team="t1", team_name="משמרת א"):
    return {"team_id": team, "team_name": team_name, "name": name,
            "person": {"name": name}, "profile": {}}


def _duty(name, day, team="t1", weight=1, type_id="k", blocks=True):
    return {"team_id": team, "employee": name, "duty_date": day.isoformat(),
            "duty_type_id": type_id, "weight": weight, "blocks": blocks}


def _fill(soldiers, dates, duties=(), shifts=None, ruled=None, types=(KITCHEN,)):
    return suggest(list(types), list(dates), soldiers, list(duties), shifts or {},
                   ruled or (lambda soldier, day: ""))


def _picks(result):
    return [(row["duty_date"], row["employee"]) for row in result["proposals"]]


def test_the_fewest_duties_first_and_the_count_moves_as_it_fills():
    soldiers = [_soldier("אבי"), _soldier("דנה"), _soldier("יוסי")]
    past = [_duty("אבי", D(2026, 11, 2)), _duty("דנה", D(2026, 11, 3)), _duty("דנה", D(2026, 11, 4))]

    result = _fill(soldiers, [MON, TUE, D(2026, 11, 18)], past)

    # יוסי had none, then אבי had one, then the tie is broken by the load.
    assert _picks(result) == [("2026-11-16", "יוסי"), ("2026-11-17", "אבי"), ("2026-11-18", "יוסי")]
    assert "בלי תורנויות" in result["proposals"][0]["reason"]


def test_a_heavier_weight_counts_more():
    soldiers = [_soldier("אבי"), _soldier("דנה")]
    past = [_duty("אבי", D(2026, 11, 2), weight=2), _duty("דנה", D(2026, 11, 3))]
    assert _picks(_fill(soldiers, [MON], past)) == [("2026-11-16", "דנה")]


def test_whoever_is_ruled_out_is_skipped_and_an_empty_seat_is_reported():
    soldiers = [_soldier("אבי"), _soldier("דנה")]
    result = _fill(soldiers, [MON], ruled=lambda soldier, day: "בבית" if soldier["name"] == "אבי" else "")
    assert _picks(result) == [("2026-11-16", "דנה")]

    nobody = _fill(soldiers, [MON], ruled=lambda soldier, day: "בבית")
    assert nobody["proposals"] == []
    assert nobody["unfilled"] == [{"duty_type_id": "k", "duty_type": "מטבח", "duty_date": "2026-11-16"}]


def test_seats_already_taken_are_not_filled_again_and_one_duty_a_day():
    two = dict(KITCHEN, seats=2)
    guard = {"id": "g", "name": "שמירה", "seats": 1, "days": [], "weight": 1, "active": True}
    soldiers = [_soldier("אבי"), _soldier("דנה"), _soldier("יוסי")]
    taken = [_duty("אבי", MON)]

    result = _fill(soldiers, [MON], taken, types=(two, guard))

    # One kitchen seat left and the guard seat: two different soldiers, not אבי.
    assert sorted(row["employee"] for row in result["proposals"]) == ["דנה", "יוסי"]


def test_fewer_shifts_and_no_shift_that_day_break_a_tie():
    soldiers = [_soldier("אבי"), _soldier("דנה")]
    shifts = {("t1", "אבי"): {D(2026, 11, 10), D(2026, 11, 11)}, ("t1", "דנה"): {D(2026, 11, 10)}}
    assert _picks(_fill(soldiers, [MON], shifts=shifts)) == [("2026-11-16", "דנה")]

    same = {("t1", "אבי"): {MON}, ("t1", "דנה"): {D(2026, 11, 10)}}
    assert _picks(_fill(soldiers, [MON], shifts=same)) == [("2026-11-16", "דנה")]


def test_weekends_are_shared_apart():
    soldiers = [_soldier("אבי"), _soldier("דנה")]
    past = [_duty("אבי", D(2026, 11, 3)), _duty("דנה", D(2026, 11, 7))]  # דנה's was a Saturday
    assert _picks(_fill(soldiers, [FRI], past)) == [("2026-11-20", "אבי")]


def test_a_kind_runs_only_on_its_days_and_a_retired_one_not_at_all():
    weekend = dict(KITCHEN, days=["שישי", "שבת"])
    retired = dict(KITCHEN, id="r", active=False)
    result = _fill([_soldier("אבי")], [MON, FRI], types=(weekend, retired))
    assert _picks(result) == [("2026-11-20", "אבי")]


def test_the_same_input_gives_the_same_answer():
    soldiers = [_soldier("דנה", "t2", "משמרת ב"), _soldier("אבי"), _soldier("יוסי", "t2", "משמרת ב")]
    first = _picks(_fill(soldiers, [MON, TUE]))
    assert first == _picks(_fill(list(reversed(soldiers)), [MON, TUE]))
    assert first[0] == ("2026-11-16", "אבי")  # משמרת א before משמרת ב


class _Ledger:
    def __init__(self, soldiers, duties, shift_days):
        self.soldiers, self.duties, self.shift_days = soldiers, duties, shift_days

    def serving(self, soldier):
        return not soldier["person"].get("inactive_from")


def test_the_balance_counts_per_soldier_team_and_kind():
    soldiers = [_soldier("אבי"), _soldier("דנה"), _soldier("נועה", "t2", "משמרת ב"),
                dict(_soldier("רון"), person={"name": "רון", "inactive_from": "2026-11-01"})]
    duties = [_duty("אבי", MON), _duty("אבי", FRI, weight=2, type_id="g"),
              _duty("נועה", TUE, team="t2", blocks=False), _duty("דנה", D(2026, 11, 1))]
    guard = {"id": "g", "name": "שמירה", "seats": 1, "days": ["שישי"], "weight": 2, "active": True}
    ledger = _Ledger(soldiers, duties, {("t1", "דנה"): {MON, TUE}})

    result = balance(ledger, [KITCHEN, guard], MON, FRI)

    people = {row["employee"]: row for row in result["people"]}
    assert "רון" not in people
    assert (people["אבי"]["duties"], people["אבי"]["duty_load"], people["אבי"]["weekend_duties"]) == (2, 3, 1)
    assert (people["נועה"]["recorded"], people["דנה"]["duties"], people["דנה"]["load"]) == (1, 0, 2)
    assert [row["employee"] for row in result["people"]][0] == "אבי"
    assert result["spread"] == {"most": 3, "least": 0, "gap": 3}
    kinds = {row["duty"]: (row["filled"], row["required"]) for row in result["types"]}
    assert kinds == {"מטבח": (1, 5), "שמירה": (1, 1)}  # a recorded duty fills no seat
    assert [(team["team_name"], team["average"]) for team in result["teams"]] == [
        ("משמרת א", 1.5), ("משמרת ב", 1.0)]
