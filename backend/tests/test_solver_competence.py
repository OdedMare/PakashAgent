"""Reservists' days a week and shifts balanced by competence."""

import pytest

from app.bl.profile_service.roster import employees
from app.bl.solver import generate_span
from app.common.errors import AgentError

MORNING, EVENING = "בוקר", "ערב"


def _person(name, group="א", **fields):
    return dict({"name": name, "exit_pattern": "round", "rotation_group": group,
                 "eligible_shifts": [MORNING, EVENING]}, **fields)


def _profile(people, shifts=(MORNING,)):
    times = {MORNING: ("07:00", "15:00"), EVENING: ("15:00", "23:00")}
    return {
        "workplace": {"name": "יחידה", "round_first_closure_date": "2026-08-29",
                      "round_first_closure_group": "א"},
        "employees": people,
        "shifts": [{"name": name, "start_time": times[name][0], "end_time": times[name][1],
                    "days": [], "staffing": [{"days": [], "headcount": 2, "required_roles": []}]}
                   for name in shifts],
    }


def _worked(result, name):
    return {row["date"] for row in result["assignments"] if row["employee"] == name}


def test_a_reservist_works_no_more_days_than_they_come():
    people = [_person("דנה"), _person("יוסי", "ב"), _person("רון", "ב"),
              _person("מילואימניק", service_type="reserve", reserve_days_per_week=1)]
    result = generate_span(_profile(people), "2026-08-31", "2026-09-02")

    assert len(_worked(result, "מילואימניק")) == 1
    assert len(result["assignments"]) == 6


def test_reservists_are_ignored_when_the_unit_switch_is_off():
    people = [_person("דנה"), _person("יוסי", "ב"),
              _person("מילואימניק", service_type="reserve", reserve_days_per_week=3)]
    profile = _profile(people)
    profile["workplace"]["reserve_enabled"] = False

    result = generate_span(profile, "2026-08-31", "2026-09-02")

    assert not _worked(result, "מילואימניק")
    assert len(result["assignments"]) == 6


def test_the_cap_is_per_sunday_week_and_counts_fixed_days():
    people = [_person("דנה"), _person("יוסי", "ב"),
              _person("מילואימניק", service_type="reserve", reserve_days_per_week=1)]
    pinned = [{"employee": "מילואימניק", "shift": MORNING, "date": "2026-08-31"}]
    result = generate_span(_profile(people), "2026-08-31", "2026-09-02",
                           required_assignments=pinned)

    assert _worked(result, "מילואימניק") == {"2026-08-31"}


def test_a_standard_soldier_ignores_reserve_days():
    people = [_person("דנה", reserve_days_per_week=1), _person("יוסי", "ב")]
    result = generate_span(_profile(people), "2026-08-31", "2026-09-02")

    assert len(_worked(result, "דנה")) == 3


@pytest.mark.parametrize("rank", ["officer", "nco"])
def test_a_standard_officer_or_nco_works_no_more_days_than_they_come(rank):
    people = [_person("דנה"), _person("יוסי", "ב"), _person("רון", "ב"),
              _person("מפקד", rank_group=rank, reserve_days_per_week=1)]
    result = generate_span(_profile(people), "2026-08-31", "2026-09-02")

    assert len(_worked(result, "מפקד")) == 1
    assert len(result["assignments"]) == 6


def test_weak_soldiers_are_not_staffed_together():
    people = [_person("חלש1", competence="weak"), _person("חלש2", "ב", competence="weak"),
              _person("חזק1", competence="excellent"), _person("חזק2", "ב", competence="excellent")]
    result = generate_span(_profile(people, (MORNING, EVENING)), "2026-08-31", "2026-08-31")

    assert len(result["assignments"]) == 4
    for shift in (MORNING, EVENING):
        crew = {row["employee"] for row in result["assignments"] if row["shift"] == shift}
        assert len([name for name in crew if name.startswith("חלש")]) == 1, crew


def test_roster_keeps_reserve_answers_only_for_reservists():
    rows = employees([
        {"name": "א", "service_type": "reserve", "reserve_days_per_week": "3",
         "reserve_call": "order", "competence": "high"},
        {"name": "ב", "service_type": "standard", "reserve_days_per_week": 3,
         "reserve_call": "days"},
    ])

    assert (rows[0]["reserve_days_per_week"], rows[0]["reserve_call"], rows[0]["competence"]) \
        == (3, "order", "high")
    assert (rows[1]["reserve_days_per_week"], rows[1]["reserve_call"], rows[1]["competence"]) \
        == (None, "", "")


def test_roster_keeps_days_a_week_for_a_standard_officer_or_nco():
    rows = employees([
        {"name": "א", "service_type": "standard", "rank_group": "officer",
         "reserve_days_per_week": 5, "reserve_min_days": 4, "reserve_consecutive": True,
         "reserve_call": "order"},
        {"name": "ב", "rank_group": "nco", "reserve_days_per_week": "5"},
        {"name": "ג", "service_type": "overlap", "rank_group": "nco", "reserve_days_per_week": 5},
    ])

    assert (rows[0]["reserve_days_per_week"], rows[0]["reserve_min_days"],
            rows[0]["reserve_consecutive"], rows[0]["reserve_call"]) == (5, 4, True, "")
    assert rows[1]["reserve_days_per_week"] == 5
    assert rows[2]["reserve_days_per_week"] is None


@pytest.mark.parametrize("field", [
    {"competence": "great"},
    {"service_type": "reserve", "reserve_days_per_week": 8},
    {"service_type": "reserve", "reserve_call": "maybe"},
    {"service_type": "reserve", "reserve_min_days": 0},
    {"service_type": "reserve", "reserve_days_per_week": 2, "reserve_min_days": 3},
    {"service_type": "reserve", "reserve_consecutive": "yes"},
])
def test_roster_refuses_unknown_values(field):
    with pytest.raises(AgentError):
        employees([dict({"name": "א"}, **field)])


# -- a dynamic reservist: how many days, and in one block ------------------

WEEK = ("2026-08-30", "2026-09-05")  # Sunday to Saturday


def _one_seat(people):
    profile = _profile(people)
    profile["shifts"][0]["staffing"][0]["headcount"] = 1
    return profile


def _regulars():
    return [_person(name, group) for name, group in
            (("דנה", "א"), ("יוסי", "ב"), ("רון", "א"), ("מיכל", "ב"), ("עדי", "א"))]


def _reservist(**fields):
    return _person("מילואימניק", service_type="reserve", **fields)


def test_a_reservist_with_a_minimum_comes_that_many_days():
    people = _regulars() + [_reservist(reserve_days_per_week=3, reserve_min_days=3)]
    result = generate_span(_one_seat(people), *WEEK)

    assert len(_worked(result, "מילואימניק")) == 3


def test_an_officer_with_a_minimum_comes_that_many_days():
    people = _regulars() + [_person("קצין", "ב", rank_group="officer",
                                    reserve_days_per_week=3, reserve_min_days=3)]
    result = generate_span(_one_seat(people), *WEEK)

    assert len(_worked(result, "קצין")) == 3


def test_without_a_minimum_evenness_decides():
    people = _regulars() + [_reservist(reserve_days_per_week=3)]
    result = generate_span(_one_seat(people), *WEEK)

    assert len(_worked(result, "מילואימניק")) < 3


def test_consecutive_days_form_one_block():
    people = _regulars() + [_reservist(reserve_days_per_week=3, reserve_min_days=3,
                                       reserve_consecutive=True)]
    result = generate_span(_one_seat(people), *WEEK)

    days = sorted(_worked(result, "מילואימניק"))
    assert len(days) == 3
    ordinals = [int(day[-2:]) if day >= "2026-09-01" else int(day[-2:]) - 31 for day in days]
    assert ordinals == list(range(ordinals[0], ordinals[0] + 3)), days


def test_a_week_cut_by_the_span_owes_no_minimum():
    people = _regulars() + [_reservist(reserve_days_per_week=3, reserve_min_days=3)]
    result = generate_span(_one_seat(people), "2026-08-30", "2026-09-01")

    assert not any("מילואים" in note for note in result["notes"])


def test_fixed_days_around_a_gap_stay_feasible():
    people = _regulars() + [_reservist(reserve_days_per_week=3, reserve_consecutive=True)]
    pinned = [{"employee": "מילואימניק", "shift": MORNING, "date": "2026-08-30"},
              {"employee": "מילואימניק", "shift": MORNING, "date": "2026-09-01"}]
    result = generate_span(_one_seat(people), *WEEK, required_assignments=pinned)

    worked = _worked(result, "מילואימניק")
    assert {"2026-08-30", "2026-09-01"} <= worked
    # Nothing past the block: the third day, if any, is the gap closed.
    assert worked <= {"2026-08-30", "2026-08-31", "2026-09-01"}


def test_roster_keeps_minimum_and_block_only_for_reservists():
    rows = employees([
        {"name": "א", "service_type": "reserve", "reserve_days_per_week": 3,
         "reserve_min_days": "2", "reserve_consecutive": True},
        {"name": "ב", "service_type": "standard", "reserve_min_days": 2,
         "reserve_consecutive": True},
    ])

    assert (rows[0]["reserve_min_days"], rows[0]["reserve_consecutive"]) == (2, True)
    assert (rows[1]["reserve_min_days"], rows[1]["reserve_consecutive"]) == (None, False)


def _rows(name, dates, shift=MORNING):
    return [{"employee": name, "shift": shift, "date": day} for day in dates]


def test_the_audit_warns_when_a_reservist_passes_their_week():
    """The solver never builds this week; a pin, a hand placement or a chat
    cover can, and the audit must say so."""
    from app.bl.audit import audit
    profile = _profile([_person("מילואימניק", service_type="reserve", reserve_days_per_week=2)])
    rows = _rows("מילואימניק", ["2026-08-30", "2026-08-31", "2026-09-01"])

    found = [w for w in audit(rows, profile["shifts"], profile["employees"], profile=profile)
             if w["code"] == "reserve_days"]

    assert len(found) == 1
    assert found[0]["details"] == {"week": "2026-08-30", "days": 3, "max": 2}


def test_the_audit_counts_days_not_shifts_and_resets_on_sunday():
    from app.bl.audit import audit
    profile = _profile([_person("מילואימניק", service_type="reserve", reserve_days_per_week=2)],
                       (MORNING, EVENING))
    # Two shifts on one day, then Saturday and the next Sunday: never 3 days in one week.
    rows = _rows("מילואימניק", ["2026-08-31"]) + _rows("מילואימניק", ["2026-08-31"], EVENING) \
        + _rows("מילואימניק", ["2026-09-05", "2026-09-06"])

    found = [w for w in audit(rows, profile["shifts"], profile["employees"], profile=profile)
             if w["code"] == "reserve_days"]

    assert found == []


def test_a_pin_past_the_week_is_reported_in_the_build():
    people = [_person("דנה"), _person("יוסי", "ב"),
              _person("מילואימניק", service_type="reserve", reserve_days_per_week=1)]
    pinned = _rows("מילואימניק", ["2026-08-31", "2026-09-01"])
    result = generate_span(_profile(people), "2026-08-31", "2026-09-02",
                           required_assignments=pinned)

    assert [w for w in result["warnings"] if w["code"] == "reserve_days"]


def test_the_picker_does_not_offer_a_reservist_whose_week_is_full():
    from app.bl.placement import check
    profile = _profile([_person("דנה"), _person("מילואימניק", service_type="reserve",
                                                  reserve_days_per_week=2)])
    schedule = {"assignments": _rows("מילואימניק", ["2026-08-31", "2026-09-01"])}

    verdict = check(schedule, profile, "מילואימניק", MORNING, "2026-09-02")

    assert not verdict["ok"]
    assert any("מילואים" in reason for reason in verdict["reasons"])


def test_a_strong_shift_gets_the_strong_soldiers():
    people = [_person("חלש1", competence="weak"), _person("חלש2", "ב", competence="medium"),
              _person("חזק1", competence="high"), _person("חזק2", "ב", competence="excellent")]
    profile = _profile(people, (MORNING, EVENING))
    profile["shifts"][0]["min_competence"] = "high"
    result = generate_span(profile, "2026-08-31", "2026-08-31")

    morning = {row["employee"] for row in result["assignments"] if row["shift"] == MORNING}
    assert morning == {"חזק1", "חזק2"}
    assert not [w for w in result["warnings"] if w["code"] == "below_level"]


def test_a_strong_shift_is_still_staffed_when_nobody_strong_is_free():
    people = [_person("חלש1", competence="weak"), _person("חזק1", "ב", competence="high"),
              _person("לא_מדורג")]
    profile = _profile(people)
    profile["shifts"][0]["min_competence"] = "high"
    result = generate_span(profile, "2026-08-31", "2026-08-31")

    # Two seats, one strong soldier: coverage first, so the unrated soldier
    # (never "below") takes the other seat rather than the weak one.
    assert {row["employee"] for row in result["assignments"]} == {"חזק1", "לא_מדורג"}
