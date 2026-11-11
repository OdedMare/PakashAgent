"""Closure shapes the setup screen offers, and the weekends it previews."""

import datetime

from app.bl import rotation
from app.bl.profile_service.workplace import workplace
from app.bl.scheduler import effective_availability


def window(**patch):
    return dict(dict(pattern="round", group="א", start_day=-2, start_time="00:00",
                     end_day=1, end_time="08:00", starts_on="", ends_on=""), **patch)


def profile(*windows):
    return {
        "workplace": {
            "round_first_closure_date": "2026-08-29", "round_first_closure_group": "א",
            "rotation_closure_windows": list(windows),
        },
        "employees": [dict(name="אלף", exit_pattern="round", rotation_group="א"),
                      dict(name="בית", exit_pattern="round", rotation_group="ב")],
        "shifts": [dict(name=name, start_time=start, end_time=end, days=[])
                   for name, start, end in [("בוקר", "08:00", "16:00"), ("לילה", "16:00", "08:00")]],
    }


def blocked(p, date):
    return {(row["employee"], row["shift"])
            for row in effective_availability(p, [], date, date)
            if row.get("source") in ("rotation", "closure")}


def test_week_on_week_off_holds_the_whole_week_for_one_group():
    # Sunday 08:00 to the next Sunday 08:00: the weeks tile, one group in each.
    p = profile(window(start_day=-6, end_day=1))
    tuesday = blocked(p, "2026-08-25")
    assert ("בית", "בוקר") in tuesday and ("בית", "לילה") in tuesday
    assert not any(name == "אלף" for name, _ in tuesday)
    next_tuesday = blocked(p, "2026-09-01")
    assert ("אלף", "בוקר") in next_tuesday
    assert not any(name == "בית" for name, _ in next_tuesday)


def test_one_weekend_from_friday_leaves_its_thursday_open():
    p = profile(window(), window(start_day=-1, starts_on="2026-08-29", ends_on="2026-08-29"))
    # Thursday's day shift is anyone's; its night runs into Friday's closure.
    assert {name for name, shift in blocked(p, "2026-08-27") if shift == "בוקר"} == set()
    assert ("בית", "בוקר") in blocked(p, "2026-08-28")
    # The weekend after is back on the regular Thursday start.
    assert ("אלף", "בוקר") in blocked(p, "2026-09-03")
    assert rotation.closing_group(p, datetime.date(2026, 9, 5)) == "ב"


def test_preview_says_where_each_weekends_hours_come_from():
    p = profile(window(), window(start_day=-1, starts_on="2026-09-05", ends_on="2026-09-05", note="חג"))
    weeks = rotation.weekend_preview(p, "round", datetime.date(2026, 8, 25), 3)
    assert [(w["saturday"], w["group"], w["kind"]) for w in weeks] == [
        ("2026-08-29", "א", "regular"), ("2026-09-05", "ב", "exception"),
        ("2026-09-12", "א", "regular")]
    assert weeks[1]["start_date"] == "2026-09-04" and weeks[1]["note"] == "חג"
    assert weeks[0]["label"] == "סבב א"


def test_preview_default_runs_thursday_to_the_sunday_handover():
    weeks = rotation.weekend_preview(profile(), "round", datetime.date(2026, 8, 29), 1)
    assert weeks == [dict(saturday="2026-08-29", group="א", label="סבב א", kind="default",
                          start_date="2026-08-27", start_time="", end_date="2026-08-30",
                          end_time="", handover_shifts=["בוקר"])]


def test_preview_without_an_anchor_is_empty():
    p = profile()
    p["workplace"]["round_first_closure_date"] = ""
    assert rotation.weekend_preview(p, "round", datetime.date(2026, 8, 29), 4) == []


def test_a_closure_window_keeps_its_name():
    saved = workplace({"rotation_closure_windows": [window(note="  פסח ")]})
    assert saved["rotation_closure_windows"][0]["note"] == "פסח"
