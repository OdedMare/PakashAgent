import pytest

from app.bl.scheduler.scheduler import Scheduler
from app.bl.shift_sequences import compile_rule
from app.common.errors import AgentError

RULES = [
    "אין לשבץ בוקר אחרי לילה", "אין לשבץ ערב אחרי לילה", "אין לשבץ 3 ערבים רצוף",
    "אין לשבץ לילה לפני יציאה הביתה", "אין לשבץ קצינים ליותר מ-6 משמרות בחודש",
    "אין לשבץ משמרת בזמן אי-זמינות שחייל או קצין מגישים",
    "אין לשבץ מסילה בבוקר שבו עולים לבסיס", "אין לשבץ לילה מיד אחרי ערב",
    "אין לשבץ שני לילות רצוף",
]


def profile():
    cycle = dict(id="c", base_days=11, home_days=3, groups=["א", "ב"], offsets={},
                 anchor_date="2026-11-01", leave_time="13:00", return_time="07:00")
    return dict(workplace={"day_cycles": [cycle]},
                employees=[dict(name="מסילה", rank_group="officer", exit_pattern="cycle:c", rotation_group="א")],
                shifts=[dict(name=name, start_time=start, end_time=end, days=[],
                             staffing=[{"days": [], "headcount": 1}])
                        for name, start, end in [("בוקר", "09:00", "17:00"),
                                                 ("ערב", "17:00", "01:00"),
                                                 ("לילה", "01:00", "09:00")]],
                rules=[{"text": text, "priority": "soft" if i == 1 else "hard"} for i, text in enumerate(RULES)],
                audit_policy={"min_rest_hours": 0})


def pin(day, shift):
    return {"employee": "מסילה", "date": day, "shift": shift}


@pytest.mark.parametrize("first,last,pins", [
    ("03","03",[("03","לילה"),("03","בוקר")]),
    ("03","04",[("03","ערב"),("04","לילה")]),
    ("03","05",[("03","ערב"),("04","ערב"),("05","ערב")]),
    ("03","04",[("03","לילה"),("04","לילה")]),
    ("12","12",[("12","לילה")]),
    ("15","15",[("15","בוקר")]),
])
def test_conflicting_pins_are_refused(first, last, pins):
    with pytest.raises(AgentError, match="שיבוץ חובה"):
        Scheduler(None).generate_span(profile(), "2026-11-"+first, "2026-11-"+last,
            required_assignments=[pin("2026-11-"+day, shift) for day, shift in pins])


def test_all_rules_build_offline_when_the_return_subject_is_defined():
    result = Scheduler(None).generate_span(profile(), "2026-11-01", "2026-11-16")
    assert result["metrics"].get("model_calls", 0) == 0
    assert 0 < len(result["assignments"]) <= 6


def test_unidentified_return_subject_is_not_compiled_as_everyone():
    p = profile()
    p["employees"][0]["name"] = "אחר"
    assert compile_rule(p["rules"][6], p) is None
    with pytest.raises(AgentError, match="מסילה"):
        Scheduler(None).generate_span(p, "2026-11-03", "2026-11-03")


def test_daily_limit_takes_precedence_over_soft_sequence_and_blocked_time_crosses_midnight():
    p = profile()
    p["rules"] = [p["rules"][1], p["rules"][5]]
    result = Scheduler(None).generate_span(p, "2026-11-03", "2026-11-03",
        required_assignments=[pin("2026-11-03","לילה")])
    assert [r["shift"] for r in result["assignments"]] == ["לילה"]
    blocked = dict(employee="מסילה", date="2026-11-04", available=False, is_hard=False,
                   start_time="00:05", end_time="00:15")
    result = Scheduler(None).generate_span(p, "2026-11-03", "2026-11-03", availability=[blocked])
    assert all(r["shift"] != "ערב" for r in result["assignments"])


def test_translated_transition_uses_declared_order_at_midnight():
    from app.bl.solver import generate_span
    p = profile()
    p["rules"] = []
    request = dict(kind="avoid_transition", shifts=["ערב", "לילה"], employees=[],
                   is_hard=True, reason="מנוחה אחרי הערב")
    result = generate_span(p, "2026-11-04", "2026-11-04", requests=[request],
                           history=[pin("2026-11-03", "ערב")])
    assert all(r["shift"] != "לילה" for r in result["assignments"])
    assert any(r["shift"] == "בוקר" for r in result["assignments"])


def test_eight_identified_rules_build_for_a_mixed_roster_without_translation():
    from collections import Counter
    from datetime import date, timedelta
    p = profile()
    p["rules"] = [r for r in p["rules"] if "מסילה" not in r["text"]]
    p["employees"] = [
        dict(name="עובד %d" % n, exit_pattern="cycle:c", rotation_group="אב"[n % 2],
             rank_group="officer" if n < 3 else "")
        for n in range(9)
    ]
    # The overnight evening on the third also overlaps this absence on the fourth.
    blocked = dict(employee="עובד 0", date="2026-11-04", available=False,
                   start_time="00:00", end_time="12:00", is_hard=False)
    result = Scheduler(None).generate_verified(p, "2026-11-01", "2026-11-21", availability=[blocked])
    rows = result["assignments"]
    assert rows
    counts = Counter(r["employee"] for r in rows)
    assert all(counts["עובד %d" % n] <= 6 for n in range(3))
    booked = {(r["employee"], date.fromisoformat(r["date"]), r["shift"]) for r in rows}
    one = timedelta(days=1)
    for name, day, shift in booked:
        if shift == "לילה":
            assert (name, day, "בוקר") not in booked
            assert (name, day - one, "ערב") not in booked
            assert (name, day - one, "לילה") not in booked
        if shift == "ערב":
            assert not all((name, day - n * one, shift) in booked for n in (1, 2))
    assert ("עובד 0", date(2026, 11, 3), "ערב") not in booked
    assert ("עובד 0", date(2026, 11, 4), "בוקר") not in booked
    for n in range(9):
        for departure in ((12,) if n % 2 == 0 else (5, 19)):
            assert ("עובד %d" % n, date(2026, 11, departure), "לילה") not in booked


def test_rebuilding_the_last_day_respects_an_existing_night_in_the_next_period():
    from app.bl.solver import generate_span
    p = profile()
    p["rules"] = [p["rules"][7]]
    result = generate_span(p, "2026-11-03", "2026-11-03", history=[pin("2026-11-04", "לילה")])
    assert all(row["shift"] != "ערב" for row in result["assignments"])


def test_manual_move_and_board_audit_use_the_same_evening_to_night_rule():
    from app.bl.audit import audit
    from app.bl.schedule_service.operations import assert_no_hard_constraint
    from app.common.errors import ConflictError

    p = profile()
    p["rules"] = [p["rules"][7]]
    earlier = dict(pin("2026-11-03", "ערב"), id="earlier")
    later = pin("2026-11-04", "לילה")
    period = dict(id="week", starts_on="2026-11-01", ends_on="2026-11-07")
    slot = dict(p["shifts"][2], shift_name="לילה", slot_date=later["date"])

    class Repo:
        def team_profile(self, team):
            return p

        def list_schedules(self, team):
            return [period]

        def assignments(self, schedule_id, team):
            return [earlier]

        def availability(self, *args):
            return []

    with pytest.raises(ConflictError, match="לילה מיד אחרי ערב"):
        assert_no_hard_constraint(Repo(), "team", period, "מסילה", slot)
    assert_no_hard_constraint(Repo(), "team", period, "מסילה", slot, moving_id="earlier")
    warnings = audit([earlier, later], p["shifts"], p["employees"], profile=p)
    assert any(w["code"] == "shift_sequence" and w["date"] == later["date"] for w in warnings)
