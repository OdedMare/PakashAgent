"""A reserve unit's staffing standard: role counts, fallback roles, ratings,
dated qualifications and weekly shift limits — solved, audited and imported."""

import datetime
from collections import Counter

import pytest

from app.bl.audit import audit
from app.bl.audit.unit_policy import cover, qualification_expired, weekly_limits
from app.bl.profile_service import roster
from app.bl.profile_service.unit import unit_policy
from app.bl.solver import generate_day, generate_span
from app.common.errors import AgentError

DAY = "יום"


def _person(name, roles, competence="medium", **extra):
    return dict({"name": name, "exit_pattern": "round", "rotation_group": "",
                 "eligible_shifts": [DAY], "competence": competence,
                 "qualifications": [{"role": role, "last_active": "2026-10-01"} for role in roles]},
                **extra)


def _profile(people, required, policy=None, headcount=None):
    return {
        "workplace": {"name": "יחידה"},
        "employees": people,
        "shifts": [{"name": DAY, "start_time": "08:00", "end_time": "20:00",
                    "staffing": [{"days": [], "headcount": headcount or len(required),
                                  "required_roles": required}]}],
        "unit_policy": policy or {},
    }


def _placed(result):
    return sorted(row["employee"] for row in result["assignments"])


# -- the matching ----------------------------------------------------------


def test_one_person_fills_one_role_seat():
    missing, substituted = cover([{"אלחוט", "טקסט"}], Counter({"אלחוט": 1, "טקסט": 1}), {})
    assert missing == Counter({"טקסט": 1}) or missing == Counter({"אלחוט": 1})
    assert substituted == 0


def test_a_fallback_holder_fills_only_what_first_hand_holders_cannot():
    missing, substituted = cover(
        [{"מודיעיני"}, {"מודיעיני"}], Counter({"מודיעיני": 1, "גיאוגרפי": 1}),
        {"גיאוגרפי": ["מודיעיני"]})
    assert not missing and substituted == 1


# -- the solver ------------------------------------------------------------


def test_a_role_listed_three_times_seats_three_holders():
    people = [_person("א%d" % n, ["אלחוט"]) for n in range(4)] + [_person("ט", ["טקסט"])]
    people.append(_person("כללי", []))
    result = generate_day(_profile(people, ["אלחוט"] * 3 + ["טקסט"]), "2026-11-08")
    placed = _placed(result)
    assert "ט" in placed and "כללי" not in placed
    assert sum(name.startswith("א") for name in placed) == 3


def test_a_missing_role_falls_back_to_its_second_priority_role():
    people = [_person("מ1", ["מודיעיני"]), _person("מ2", ["מודיעיני"]), _person("כללי", [])]
    policy = {"role_fallbacks": {"גיאוגרפי": ["מודיעיני"]}}
    result = generate_day(_profile(people, ["מודיעיני", "גיאוגרפי"], policy), "2026-11-08")
    assert _placed(result) == ["מ1", "מ2"]
    assert any("בעדיפות שנייה" in note for note in result["notes"])


def test_no_more_weak_people_on_a_shift_than_the_unit_allows():
    people = [_person("ג%d" % n, ["אלחוט"], competence="weak") for n in range(3)] + [_person("ב", ["אלחוט"])]
    result = generate_day(_profile(people, ["אלחוט"] * 3, {"max_weak_per_shift": 1}), "2026-11-08")
    placed = _placed(result)
    assert sum(name.startswith("ג") for name in placed) == 1
    assert "ב" in placed


def test_weekly_maximum_is_never_exceeded():
    people = [_person("p%d" % n, ["אלחוט"]) for n in range(3)]
    policy = {"weekly_shifts": {"max": 2}}
    result = generate_span(_profile(people, ["אלחוט"], policy), "2026-11-08", "2026-11-14")
    load = Counter(row["employee"] for row in result["assignments"])
    assert max(load.values()) <= 2
    assert sum(load.values()) == 6  # 7 seats, 3 people × 2: one stays short


def test_the_weekly_maximum_takes_the_allowed_overflow_then_leaves_seats_empty():
    """Max 4 and one over it: alone on a daily shift, a reservist works five
    of seven days, the fifth with a warning on that shift; two stay empty."""
    people = [_person("מ", ["אלחוט"], service_type="reserve", exit_pattern="none")]
    policy = {"weekly_shifts": {"max": 4}, "weekly_shifts_overflow": 1}
    result = generate_span(_profile(people, ["אלחוט"], policy), "2026-11-08", "2026-11-14")
    assert len(result["assignments"]) == 5
    over = [item for item in result["warnings"] if item["code"] == "weekly_shifts"]
    assert len(over) == 1 and over[0]["details"]["count"] == 5 and over[0]["details"]["within_overflow"]
    assert over[0]["date"] and over[0]["shift"] == DAY
    assert any("מעל המקסימום של 4 משמרות" in note for note in result["notes"])
    assert any("מיצו את מקסימום המשמרות בשבוע" in note for note in result["notes"])


def test_the_overflow_is_taken_only_when_a_seat_needs_it():
    people = [_person("p%d" % n, ["אלחוט"]) for n in range(2)]
    policy = {"weekly_shifts": {"max": 4}, "weekly_shifts_overflow": 1}
    result = generate_span(_profile(people, ["אלחוט"], policy), "2026-11-08", "2026-11-14")
    load = Counter(row["employee"] for row in result["assignments"])
    assert sum(load.values()) == 7 and max(load.values()) == 4
    assert not [item for item in result["warnings"] if item["code"] == "weekly_shifts"]
    assert not any("מעל המקסימום" in note for note in result["notes"])


def test_each_shift_past_the_weekly_maximum_is_warned_on_its_own():
    people = [_person("ד", ["אלחוט"])]
    profile = _profile(people, ["אלחוט"], {"weekly_shifts": {"max": 4}, "weekly_shifts_overflow": 1})
    rows = [{"employee": "ד", "shift": DAY, "date": "2026-11-%02d" % day} for day in range(8, 15)]
    over = [item for item in audit(rows, profile["shifts"], people, profile=profile)
            if item["code"] == "weekly_shifts"]
    assert [item["date"] for item in over] == ["2026-11-12", "2026-11-13", "2026-11-14"]
    assert [item["details"]["within_overflow"] for item in over] == [True, False, False]


def test_regulars_have_their_own_weekly_limits():
    policy = {"weekly_shifts": {"min": 2, "max": 3}, "weekly_shifts_regular": {"min": 4, "max": 5},
              "weekly_shifts_officers": {"min": 5, "max": 6},
              "weekly_shifts_ncos": {"min": 3, "max": 4}}
    assert weekly_limits({"unit_policy": policy}, {"service_type": "standard"}) == (4, 5)
    assert weekly_limits({"unit_policy": policy}, {"service_type": "standard", "rank_group": "officer"}) == (5, 6)
    assert weekly_limits({"unit_policy": policy}, {"service_type": "standard", "rank_group": "nco"}) == (3, 4)
    assert weekly_limits({"unit_policy": policy}, {"service_type": "reserve", "rank_group": "officer"}) == (2, 3)
    assert weekly_limits({"unit_policy": policy}, {"service_type": "reserve"}) == (2, 3)
    assert weekly_limits({"unit_policy": {"weekly_shifts": {"max": 2}}},
                         {"rank_group": "nco"}) == (0, 2)
    assert weekly_limits({"unit_policy": {"weekly_shifts_regular": {"min": 2, "max": 5},
                                          "weekly_shifts_ncos": {"min": 3}}},
                         {"rank_group": "nco"}) == (3, 5)
    assert weekly_limits({}, {}) == (0, None)


# -- the audit -------------------------------------------------------------


def test_the_audit_reports_counts_weak_crews_and_weekly_overload():
    people = [_person("ג1", ["אלחוט"], competence="weak"), _person("ג2", ["אלחוט"], competence="weak")]
    profile = _profile(people, ["אלחוט"] * 3, {"max_weak_per_shift": 1, "weekly_shifts": {"max": 1}})
    rows = [{"employee": name, "shift": DAY, "date": date}
            for name in ("ג1", "ג2") for date in ("2026-11-08", "2026-11-09")]
    codes = Counter(item["code"] for item in audit(rows, profile["shifts"], people, profile=profile))
    assert codes["missing_role"] == 2   # one short of three, on each date
    assert codes["weak_crew"] == 2
    assert codes["weekly_shifts"] == 2


def test_a_stale_qualification_is_reported_once():
    person = _person("ותיק", [], qualifications=[{"role": "אלחוט", "last_active": "2026-01-01"}])
    profile = _profile([person], ["אלחוט"])
    assert qualification_expired(profile, person, "אלחוט", datetime.date(2026, 11, 8))
    rows = [{"employee": "ותיק", "shift": DAY, "date": d} for d in ("2026-11-08", "2026-11-09")]
    warnings = audit(rows, profile["shifts"], [person], profile=profile)
    assert [w["code"] for w in warnings].count("qualification_expired") == 1


# -- the profile -----------------------------------------------------------


def test_qualifications_and_unit_policy_are_validated():
    saved = roster.employees([{"name": "דנה", "service_type": "standard",
                               "qualifications": [{"role": "טקסט", "last_active": "2026-09-01"}]}])
    assert saved[0]["qualifications"] == [{"role": "טקסט", "last_active": "2026-09-01"}]
    assert roster.employees([{"name": "יוסי", "rank_group": "nco"}])[0]["rank_group"] == "nco"
    with pytest.raises(AgentError):
        roster.employees([{"name": "יוסי", "rank_group": "soldier"}])
    with pytest.raises(AgentError):
        roster.employees([{"name": "דנה", "qualifications": [{"role": "טקסט", "last_active": "1.9"}]}])
    with pytest.raises(AgentError):
        unit_policy({"weekly_shifts": {"min": 5, "max": 2}})
    policy = unit_policy({"max_weak_per_shift": "1", "weekly_shifts_ncos": {"min": 2, "max": 4}})
    assert policy["max_weak_per_shift"] == 1
    assert policy["weekly_shifts_ncos"] == {"min": 2, "max": 4}
    assert unit_policy({"weekly_shifts_overflow": "1"})["weekly_shifts_overflow"] == 1
    with pytest.raises(AgentError):
        unit_policy({"weekly_shifts_overflow": -1})


def test_a_first_profile_without_any_weekend_cycle_needs_no_groups():
    profile = _profile([_person("דנה", ["טקסט"])], ["טקסט"])
    roster.validate_first_profile(profile)


def test_a_soldier_below_a_strong_shifts_level_is_named_on_their_own_warning():
    people = [_person("חלש", ["אלחוט"], competence="weak"), _person("חזק", ["אלחוט"], competence="high"),
              _person("לא_מדורג", ["אלחוט"], competence="")]
    profile = _profile(people, [], headcount=3)
    profile["shifts"][0]["min_competence"] = "high"
    rows = [{"employee": name, "shift": DAY, "date": "2026-11-08"} for name in ("חלש", "חזק", "לא_מדורג")]
    found = [w for w in audit(rows, profile["shifts"], people, profile=profile) if w["code"] == "below_level"]

    assert [w["employee"] for w in found] == ["חלש"]
    assert found[0]["severity"] == "warning"
    assert found[0]["details"] == {"competence": "weak", "required": "high"}
    assert "משמרת חזקה" in found[0]["message"]


def test_a_shift_with_no_level_flags_nobody():
    people = [_person("חלש", ["אלחוט"], competence="weak")]
    profile = _profile(people, [])
    rows = [{"employee": "חלש", "shift": DAY, "date": "2026-11-08"}]
    assert not [w for w in audit(rows, profile["shifts"], people, profile=profile) if w["code"] == "below_level"]
