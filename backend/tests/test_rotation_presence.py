"""Group windows constrain generation and audit before fairness."""

import datetime

import pytest

from app.bl import rotation
from app.bl.audit import CROSS_ROTATION, audit
from app.bl.profile_service.workplace import workplace
from app.bl.scheduler import Scheduler, build_slots, effective_availability
from app.bl.scheduler.bounding import bound_assignments
from app.bl.scheduler.candidates import candidates_for
from app.common.errors.errors import AgentError


def window(pattern="round", group="א", **patch):
    return dict(dict(pattern=pattern, group=group, start_day=-2, start_time="12:00",
                     end_day=1, end_time="12:00", starts_on="", ends_on=""), **patch)


def rule(group="ב", available=False, **patch):
    return dict(dict(pattern="round", group=group, available=available, days=["שני"], shifts=[],
                     start_time="", end_time="", starts_on="", ends_on="", reason=""), **patch)


def profile():
    return {
        "workplace": {
            "round_first_closure_date": "2026-08-29", "round_first_closure_group": "א",
            "triplet_first_closure_date": "2026-08-29", "triplet_first_closure_group": "ג",
            "rotation_closure_windows": [window(), window("triplet", "ג", start_time="16:00")],
        },
        "employees": [
            dict(name=name, exit_pattern=pattern, rotation_group=group)
            for name, pattern, group in [("א", "round", "א"), ("ב", "round", "ב"),
                                         ("תא", "triplet", "א"), ("תג", "triplet", "ג")]
        ],
        "shifts": [
            dict(name=name, start_time=start, end_time=end, days=[])
            for name, start, end in [("בוקר", "08:00", "12:00"), ("צהריים", "12:00", "16:00"),
                                     ("ערב", "16:00", "20:00"), ("לילה", "20:00", "08:00")]
        ],
    }


def blocked(p, date, explicit=None):
    return {(row["employee"], row["shift"])
            for row in effective_availability(p, explicit or [], date, date)
            if row.get("source") in ("rotation", "closure")}


def test_thursday_noon_to_sunday_morning_is_per_cycle_and_per_group():
    p = profile()
    thursday = blocked(p, "2026-08-27")
    assert ("ב", "בוקר") not in thursday
    assert ("ב", "צהריים") in thursday
    assert ("תא", "צהריים") not in thursday
    assert ("תא", "ערב") in thursday
    sunday = blocked(p, "2026-08-30")
    assert ("ב", "בוקר") in sunday and ("תא", "בוקר") in sunday
    assert ("ב", "צהריים") not in sunday and ("תא", "צהריים") not in sunday
    board = rotation.by_date(p, datetime.date(2026, 8, 27), datetime.date(2026, 8, 27))
    assert board["2026-08-27"]["until_handover"] is False
    assert "בוקר" not in board["2026-08-27"]["shifts"]


def test_boundary_crossing_shift_is_not_available_to_either_group():
    p = profile()
    p["shifts"] = [dict(name="חוצה", start_time="10:00", end_time="14:00")]
    assert {("א", "חוצה"), ("ב", "חוצה")} <= blocked(p, "2026-08-27")
    assert {("א", "חוצה"), ("ב", "חוצה")} <= blocked(p, "2026-08-30")


def test_dated_departure_change_expires_without_changing_cycle_phase():
    p = profile()
    p["workplace"]["rotation_closure_windows"].append(window(
        start_time="16:00", starts_on="2026-08-29", ends_on="2026-08-29"))
    assert ("ב", "צהריים") not in blocked(p, "2026-08-27")
    assert ("ב", "צהריים") in blocked(p, "2026-09-10")
    assert rotation.closing_group(p, datetime.date(2026, 9, 12)) == "א"


def test_absence_survives_employee_availability_and_model_balancing():
    p = profile()
    p["workplace"]["rotation_presence"] = [rule()]
    date = "2026-08-31"
    availability = effective_availability(p, [dict(employee="ב", date=date, available=True)], date, date)
    slots = build_slots(p, date, date)
    candidates = candidates_for(p, slots, availability)
    assert candidates["id_by_name"]["ב"] not in candidates["by_slot"]["slot-1"]
    assert bound_assignments([dict(employee="ב", date=date, shift="בוקר", reason="איזון עומסים")],
                             slots, p, availability) == []
    findings = audit([dict(employee="ב", date=date, shift="בוקר")], p["shifts"], p["employees"], profile=p)
    assert any(item["code"] == CROSS_ROTATION for item in findings)


def test_dated_presence_overrides_recurring_absence_only_in_its_period():
    p = profile()
    p["workplace"]["rotation_presence"] = [rule(), rule(available=True, starts_on="2026-08-31", ends_on="2026-08-31")]
    assert ("ב", "בוקר") not in blocked(p, "2026-08-31")
    assert ("ב", "בוקר") in blocked(p, "2026-09-07")


def test_presence_can_define_a_fixed_weekend_independently_of_cycle_phase():
    p = profile()
    p["workplace"]["rotation_presence"] = [rule("א", True, days=["שבת"]), rule("ב", days=["שבת"])]
    assert ("א", "בוקר") not in blocked(p, "2026-09-05")
    assert ("ב", "בוקר") in blocked(p, "2026-09-05")


def test_overnight_absence_covers_the_next_morning_and_the_previous_night():
    p = profile()
    p["shifts"].append(dict(name="לפנות בוקר", start_time="04:00", end_time="06:00"))
    p["workplace"]["rotation_presence"] = [rule(start_time="22:00", end_time="06:00")]
    assert ("ב", "לפנות בוקר") in blocked(p, "2026-09-01")
    assert ("ב", "בוקר") not in blocked(p, "2026-09-01")
    p["workplace"]["rotation_presence"] = [rule(days=["שלישי"], end_time="06:00")]
    assert ("ב", "לילה") in blocked(p, "2026-08-31")


def test_closing_group_missing_from_roster_never_frees_the_other_group():
    p = profile()
    p["employees"] = [p["employees"][1]]
    assert ("ב", "צהריים") in blocked(p, "2026-08-27")


def test_presence_over_multiple_days_keeps_overnight_shifts_available():
    p = profile()
    p["workplace"]["rotation_presence"] = [rule("א", True, days=["שישי", "שבת"])]
    assert ("א", "לילה") not in blocked(p, "2026-09-04")


def test_missing_shift_clocks_cannot_bypass_a_configured_closure():
    p = profile()
    p["shifts"] = [{"name": "ללא שעות"}]
    assert {("א", "ללא שעות"), ("ב", "ללא שעות")} <= blocked(p, "2026-08-29")


@pytest.mark.parametrize("method", ["generate", "generate_span", "generate_verified"])
def test_all_model_generation_paths_require_an_anchor(method):
    p = profile()
    p["workplace"]["triplet_first_closure_date"] = ""
    with pytest.raises(AgentError, match="תלתון"):
        getattr(Scheduler(None), method)(p, "2026-08-29", "2026-08-29")


@pytest.mark.parametrize("method", ["generate", "generate_span", "generate_verified"])
def test_pinned_assignments_cannot_override_group_absence(method):
    p = profile()
    with pytest.raises(AgentError, match="נוכחות"):
        getattr(Scheduler(None), method)(p, "2026-08-29", "2026-08-29",
                                       required_assignments=[dict(employee="ב", shift="בוקר", date="2026-08-29")])


@pytest.mark.parametrize("patch", [{"group": "ג"}, {"start_time": "25:00"},
                                     {"starts_on": "2026-09-01", "ends_on": "2026-08-01"},
                                     {"start_day": True}, {"end_day": -1},
                                     {"start_day": 0, "end_day": 0, "start_time": "14:00"}])
def test_invalid_group_windows_are_rejected_on_save(patch):
    with pytest.raises(AgentError):
        workplace({"rotation_closure_windows": [window(**patch)]})
