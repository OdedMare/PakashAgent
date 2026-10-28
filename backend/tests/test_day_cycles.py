"""Day-based cycles (11/3, 12/2, שבוע־שבוע) as hard availability."""

import datetime

import pytest

from app.bl import rotation
from app.bl.audit import CROSS_ROTATION, audit
from app.bl.profile_service import roster
from app.bl.profile_service.workplace import workplace
from app.bl.rotation import day_cycles
from app.bl.scheduler import Scheduler, effective_availability
from app.bl.solver import generate_span
from app.common.errors import AgentError


def cycle(**patch):
    # Sunday 1.11: group א starts eleven days on base.
    return dict(dict(id="c1", name="11/3", base_days=11, home_days=3,
                     anchor_date="2026-11-01", groups=["א", "ב"], offsets={},
                     leave_time="", return_time=""), **patch)


def profile(**patch):
    return {
        "workplace": {"day_cycles": [cycle(**patch)]},
        "employees": [dict(name="אבי", exit_pattern="cycle:c1", rotation_group="א"),
                      dict(name="בני", exit_pattern="cycle:c1", rotation_group="ב")],
        "shifts": [dict(name=name, start_time=start, end_time=end, days=[])
                   for name, start, end in [("בוקר", "08:00", "16:00"), ("ערב", "16:00", "00:00")]],
    }


def blocked(p, date):
    return {(row["employee"], row["shift"])
            for row in effective_availability(p, [], date, date)
            if row.get("source") in ("rotation", "closure")}


def home(p, name, date):
    return {(name, "בוקר"), (name, "ערב")} <= blocked(p, date)


def test_eleven_three_sends_each_group_home_on_alternating_weekends():
    p = profile()
    # Group ב is half a cycle behind: home Thursday-Saturday of week one.
    for date in ("2026-11-05", "2026-11-06", "2026-11-07"):
        assert home(p, "בני", date) and not blocked(p, date) & {("אבי", "בוקר")}
    # Group א goes home Thursday-Saturday of week two; ב holds that weekend.
    for date in ("2026-11-12", "2026-11-13", "2026-11-14"):
        assert home(p, "אבי", date) and not blocked(p, date) & {("בני", "בוקר")}
    assert not blocked(p, "2026-11-15") and not blocked(p, "2026-11-11")
    # And again a full cycle later.
    assert home(p, "אבי", "2026-11-26") and home(p, "בני", "2026-11-19")


def test_leave_and_return_times_share_the_transition_day():
    p = profile(leave_time="14:00", return_time="12:00")
    thursday, sunday = blocked(p, "2026-11-12"), blocked(p, "2026-11-15")
    assert ("אבי", "בוקר") in thursday and ("אבי", "ערב") in thursday
    p = profile(leave_time="16:00", return_time="12:00")
    assert ("אבי", "בוקר") not in blocked(p, "2026-11-12")
    assert ("אבי", "ערב") in blocked(p, "2026-11-12")
    assert ("אבי", "בוקר") in sunday and ("אבי", "ערב") not in sunday


@pytest.mark.parametrize("base,home_days,groups,offsets", [
    (7, 7, ["א", "ב"], {}),
    (12, 2, ["א", "ב"], {}),
    (14, 7, ["א", "ב", "ג"], {}),
    (11, 3, ["א", "ב"], {"ב": 11}),
])
def test_every_group_is_home_exactly_home_days_per_cycle(base, home_days, groups, offsets):
    c = cycle(base_days=base, home_days=home_days, groups=groups, offsets=offsets)
    first = datetime.date(2026, 11, 1)
    for group in groups:
        days = [first + datetime.timedelta(days=n) for n in range(base + home_days)]
        assert sum(not day_cycles.on_base(c, group, day) for day in days) == home_days


def test_default_offsets_spread_groups_and_week_week_never_overlaps():
    c = cycle(base_days=7, home_days=7)
    assert day_cycles.offset(c, "ב") == 7
    for n in range(28):
        day = datetime.date(2026, 11, 1) + datetime.timedelta(days=n)
        assert day_cycles.on_base(c, "א", day) != day_cycles.on_base(c, "ב", day)


def test_dates_before_the_anchor_follow_the_same_cycle():
    p = profile()
    assert home(p, "אבי", "2026-10-29") and home(p, "בני", "2026-10-22")


def test_solver_and_audit_respect_the_cycle():
    p = profile()
    result = generate_span(p, "2026-11-12", "2026-11-14")
    assert "אבי" not in {row["employee"] for row in result["assignments"]}
    findings = audit([dict(employee="אבי", date="2026-11-13", shift="בוקר")],
                     p["shifts"], p["employees"], profile=p)
    found = [item for item in findings if item["code"] == CROSS_ROTATION]
    assert found and "11/3 א" in found[0]["message"]


def test_dated_presence_rule_moves_one_transition():
    p = profile()
    p["workplace"]["rotation_presence"] = [dict(
        pattern="cycle:c1", group="א", available=True, days=[], shifts=[],
        start_time="", end_time="", starts_on="2026-11-12", ends_on="2026-11-12", reason="")]
    assert not blocked(p, "2026-11-12") & {("אבי", "בוקר")}
    assert home(p, "אבי", "2026-11-13")


def test_unanchored_or_unknown_cycle_cannot_be_generated():
    p = profile(anchor_date="")
    assert any("עוגן" in error for error in rotation.configuration_errors(p))
    with pytest.raises(AgentError):
        Scheduler(None).generate_span(p, "2026-11-12", "2026-11-12")
    p = profile()
    p["employees"][0]["exit_pattern"] = "cycle:missing"
    assert any("אינו מוגדר" in error for error in rotation.configuration_errors(p))


def test_workplace_normalises_cycles_and_names_them():
    saved = workplace({"day_cycles": [dict(base_days=12, home_days=2, groups=["א", "ב", "ב"],
                                           leave_time="9:00")]})
    row = saved["day_cycles"][0]
    assert row["id"] == "c1" and row["name"] == "12/2" and row["groups"] == ["א", "ב"]
    assert row["leave_time"] == "09:00" and row["offsets"] == {}


@pytest.mark.parametrize("patch", [
    {"base_days": 0}, {"home_days": "3"}, {"base_days": 100, "home_days": 30},
    {"anchor_date": "1.11"}, {"offsets": {"ג": 1}}, {"offsets": {"ב": 14}},
    {"leave_time": "25:00"}, {"id": "a b"}, {"groups": "א"},
])
def test_invalid_cycles_are_rejected(patch):
    with pytest.raises(AgentError):
        workplace({"day_cycles": [cycle(**patch)]})


def test_closure_windows_are_only_for_weekend_cycles():
    with pytest.raises(AgentError):
        workplace({"day_cycles": [cycle()], "rotation_closure_windows": [dict(
            pattern="cycle:c1", group="א", start_day=-2, start_time="12:00",
            end_day=1, end_time="12:00")]})


def test_roster_accepts_a_cycle_and_checks_its_group():
    p = profile()
    p["workplace"] = workplace(p["workplace"])
    p["employees"] = roster.employees(p["employees"])
    roster.validate_rotation_groups(p)
    p["employees"][0]["rotation_group"] = "ג"
    with pytest.raises(AgentError):
        roster.validate_rotation_groups(p)
    p["employees"][0].update(exit_pattern="cycle:other", rotation_group="א")
    with pytest.raises(AgentError):
        roster.validate_rotation_groups(p)


def test_a_unit_can_run_weekend_and_day_cycles_together():
    p = profile()
    p["workplace"].update(round_first_closure_date="2026-11-07", round_first_closure_group="א")
    p["employees"].append(dict(name="רון", exit_pattern="round", rotation_group="ב"))
    assert rotation.configuration_errors(p) == []
    # Round א closes 7.11, so round ב is out; the 11/3 people follow their own cycle.
    assert ("רון", "בוקר") in blocked(p, "2026-11-07")
    assert ("אבי", "בוקר") not in blocked(p, "2026-11-07")


def test_departure_can_move_to_the_previous_evening():
    # 11/3 leaving Wednesday at 18:00 instead of Thursday morning.
    p = profile(leave_day=-1, leave_time="18:00")
    assert ("אבי", "ערב") in blocked(p, "2026-11-11")
    assert ("אבי", "בוקר") not in blocked(p, "2026-11-11")


def test_each_group_can_keep_its_own_hours():
    p = profile(leave_time="16:00",
                group_times={"ב": {"leave_time": "08:00", "return_day": 1, "return_time": "08:00"}})
    assert ("אבי", "בוקר") not in blocked(p, "2026-11-12")
    assert ("בני", "בוקר") in blocked(p, "2026-11-05")
    # ב comes back a day late, on Monday morning.
    assert home(p, "בני", "2026-11-08")
    assert not blocked(p, "2026-11-09") & {("בני", "בוקר")}


def test_a_dated_change_moves_one_departure_only():
    p = profile(time_changes=[dict(group="א", starts_on="2026-11-12", ends_on="2026-11-12",
                                   leave_day=1, leave_time="12:00")])
    # Holiday week: א leaves Friday at noon instead of Thursday.
    assert not blocked(p, "2026-11-12") & {("אבי", "בוקר"), ("אבי", "ערב")}
    assert ("אבי", "בוקר") in blocked(p, "2026-11-13")
    # The next stretch is back to normal.
    assert home(p, "אבי", "2026-11-26")


def test_timing_layers_are_validated_on_save():
    saved = workplace({"day_cycles": [cycle(
        leave_day=-1, leave_time="18:00",
        group_times={"ב": {"return_time": "10:00"}},
        time_changes=[dict(starts_on="2026-12-01", leave_time="12:00")])]})["day_cycles"][0]
    assert saved["group_times"] == {"ב": {"return_time": "10:00"}}
    assert saved["time_changes"][0]["group"] == "" and saved["time_changes"][0]["leave_time"] == "12:00"


@pytest.mark.parametrize("patch", [
    {"leave_day": 4}, {"return_day": True},
    {"group_times": {"ג": {"leave_time": "10:00"}}},
    {"time_changes": [dict(leave_time="10:00")]},
    {"time_changes": [dict(starts_on="2026-12-02", ends_on="2026-12-01")]},
    # Home only one day, and the return is moved before the departure.
    {"home_days": 1, "leave_time": "12:00", "return_day": -1},
    # 2/1 leaving two days early leaves no time on base.
    {"base_days": 2, "home_days": 1, "leave_day": -2, "return_day": 1},
])
def test_impossible_timings_are_rejected(patch):
    with pytest.raises(AgentError):
        workplace({"day_cycles": [cycle(**patch)]})
