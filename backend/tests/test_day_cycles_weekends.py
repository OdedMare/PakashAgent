"""A unit's own 1 ל־X: X groups closing one Saturday each, in turn."""

import pytest

from app.bl import rotation
from app.bl.profile_service import roster
from app.bl.profile_service.workplace import workplace
from app.bl.scheduler import effective_availability
from app.common.errors import AgentError

GROUPS = ["א", "ב", "ג", "ד", "ה", "ו"]


def cycle(**patch):
    # Saturday 7.11 is group א's weekend; six groups, one Saturday in six.
    return dict(dict(id="w1", kind="weekends", name="1 ל־6", anchor_date="2026-11-05",
                     groups=GROUPS, leave_time="", return_time="12:00"), **patch)


def profile(**patch):
    return {
        "workplace": {"day_cycles": [cycle(**patch)]},
        "employees": [dict(name=name, exit_pattern="cycle:w1", rotation_group=group)
                      for name, group in [("אבי", "א"), ("בני", "ב"), ("ויקי", "ו")]],
        "shifts": [dict(name=name, start_time=start, end_time=end, days=[])
                   for name, start, end in [("בוקר", "08:00", "16:00"), ("ערב", "16:00", "00:00")]],
    }


def home(p, name, date):
    rows = effective_availability(p, [], date, date)
    return {(row["employee"], row["shift"]) for row in rows
            if row.get("source") in ("rotation", "closure")} >= {(name, "בוקר"), (name, "ערב")}


def test_each_group_closes_one_saturday_in_x_and_is_home_on_the_others():
    p = profile()
    # 7.11: א closes, everybody else is home Thursday to Sunday.
    assert not home(p, "אבי", "2026-11-07") and home(p, "בני", "2026-11-07") and home(p, "ויקי", "2026-11-05")
    # 14.11 is ב's; 12.12 (five weeks on) is ו's; 19.12 is א's again.
    assert home(p, "אבי", "2026-11-14") and not home(p, "בני", "2026-11-14")
    assert not home(p, "ויקי", "2026-12-12") and home(p, "אבי", "2026-12-12")
    assert not home(p, "אבי", "2026-12-19")
    # Midweek everybody is on base.
    assert not any(home(p, name, "2026-11-10") for name in ("אבי", "בני", "ויקי"))


def test_return_hour_shares_the_sunday():
    p = profile()
    rows = {(row["employee"], row["shift"]) for row in effective_availability(p, [], "2026-11-08", "2026-11-08")
            if row.get("source") in ("rotation", "closure")}
    # Home until 12:00 Sunday: the morning shift is blocked, the evening is not.
    assert ("בני", "בוקר") in rows and ("בני", "ערב") not in rows


def test_leave_day_moves_the_thursday():
    p = profile(leave_day=1)  # Friday instead of Thursday
    assert not home(p, "בני", "2026-11-05") and home(p, "בני", "2026-11-06")


def test_workplace_normalises_a_weekend_cycle():
    row = workplace({"day_cycles": [dict(kind="weekends", groups=GROUPS[:4], offsets={"ב": 3})]})["day_cycles"][0]
    assert row["kind"] == "weekends" and row["name"] == "1 ל־4" and row["offsets"] == {}
    assert row["base_days"] == 7 and row["home_days"] == 21
    assert workplace({"day_cycles": [dict(base_days=11, home_days=3)]})["day_cycles"][0]["kind"] == "days"


@pytest.mark.parametrize("patch", [
    {"groups": ["א"]}, {"groups": ["א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט"]},
    {"kind": "months"}, {"leave_day": 3, "return_day": -3, "return_time": ""},
])
def test_invalid_weekend_cycles_are_rejected(patch):
    with pytest.raises(AgentError):
        workplace({"day_cycles": [cycle(**patch)]})


def test_roster_accepts_its_groups_and_an_unanchored_one_cannot_build():
    p = profile()
    p["workplace"] = workplace(p["workplace"])
    p["employees"] = roster.employees(p["employees"])
    roster.validate_rotation_groups(p)
    p["employees"][0]["rotation_group"] = "ז"
    with pytest.raises(AgentError):
        roster.validate_rotation_groups(p)
    assert any("השבת שבה קבוצה א סוגרת" in error
               for error in rotation.configuration_errors(profile(anchor_date="")))
