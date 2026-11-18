"""Rest, runs, even shares and company as structured requests (D32, step 2)."""

import datetime
import json

from app.bl.solver import generate_span
from app.bl.directive_agent import DirectiveAgent
from app.bl.schedule_requests import read_requests
from app.bl.scheduler.scheduler import Scheduler

MORNING, NIGHT = "בוקר", "לילה"
SUNDAY, SATURDAY = "2026-08-16", "2026-08-22"
PEOPLE = ("דנה", "יוסי", "רון", "מאיה", "נועה")


def _profile(people=PEOPLE, morning=1, night=1, **extra):
    profile = {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": name} for name in people],
        "shifts": [
            {"name": MORNING, "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": morning, "required_roles": []}]},
            {"name": NIGHT, "start_time": "23:00", "end_time": "07:00", "days": [],
             "staffing": [{"days": [], "headcount": night, "required_roles": []}]},
        ],
    }
    profile.update(extra)
    return profile


def _request(kind, employees=(), count=None, shifts=(), weekdays=(), partners=(),
             hard=True, weight=1):
    return {"kind": kind, "employees": list(employees), "partners": list(partners),
            "shifts": list(shifts), "dates": [], "weekdays": list(weekdays), "count": count,
            "per": "period", "is_hard": hard, "weight": weight, "reason": "בדיקה"}


def _errors(*requests):
    return read_requests(list(requests), _profile())[1]


def _times(row):
    day = datetime.date.fromisoformat(row["date"])
    if row["shift"] == MORNING:
        return (datetime.datetime.combine(day, datetime.time(7)),
                datetime.datetime.combine(day, datetime.time(15)))
    return (datetime.datetime.combine(day, datetime.time(23)),
            datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time(7)))


def _rests(rows):
    by_person = {}
    for row in rows:
        by_person.setdefault(row["employee"], []).append(_times(row))
    gaps = []
    for spans in by_person.values():
        spans.sort()
        gaps += [(later[0] - earlier[1]).total_seconds() / 3600
                 for earlier, later in zip(spans, spans[1:])]
    return gaps


def _longest_run(rows, employee, shift=None):
    days = sorted({datetime.date.fromisoformat(row["date"]) for row in rows
                   if row["employee"] == employee and (shift is None or row["shift"] == shift)})
    best = run = 0
    for index, day in enumerate(days):
        run = run + 1 if index and (day - days[index - 1]).days == 1 else 1
        best = max(best, run)
    return best


def test_team_wide_kinds_may_name_nobody_and_the_rest_may_not():
    assert _errors(_request("min_rest", count=12), _request("max_consecutive", count=3),
                   _request("balance", hard=False)) == []
    assert _errors(_request("avoid"))
    assert _errors(_request("balance", employees=["דנה"], hard=False))


def test_each_new_kind_is_held_to_its_own_shape():
    assert _errors(_request("balance"))  # An even share is only ever a wish.
    assert _errors(_request("min_rest", count=0))
    assert _errors(_request("min_rest", count=100))
    assert _errors(_request("max_consecutive", count=0))
    assert _errors(_request("max_consecutive", count=2.5))
    assert _errors(_request("requires_with", employees=["נועה"]))
    assert _errors(_request("requires_with", employees=["נועה"], partners=["נועה"]))
    assert _errors(_request("requires_with", employees=["נועה"], partners=["רפאל"]))
    assert _errors(_request("avoid", employees=["דנה"], partners=["יוסי"]))
    assert _errors(_request("requires_with", employees=["נועה"], partners=["דנה"])) == []
    assert _errors(_request("min_rest", count=11.5)) == []


def test_a_hard_minimum_rest_holds_across_the_week():
    # Two people for two shifts a day, with the profile's own rest limit off:
    # left alone, code puts someone on a morning eight hours after a night.
    profile = _profile(PEOPLE[:2], audit_policy={"min_rest_hours": 0, "max_consecutive_days": 7})
    alone = generate_span(profile, SUNDAY, SATURDAY)
    rested = generate_span(profile, SUNDAY, SATURDAY, requests=[_request("min_rest", count=16)])

    assert min(_rests(alone["assignments"])) < 16
    assert min(_rests(rested["assignments"])) >= 16


def _gaps(rows, people):
    """(hours of rest, whether a night is on either side) per consecutive pair."""
    found = []
    for employee in people:
        spans = sorted((_times(row), row["shift"]) for row in rows if row["employee"] == employee)
        for (earlier, first), (later, second) in zip(spans, spans[1:]):
            found.append(((later[0] - earlier[1]).total_seconds() / 3600, NIGHT in (first, second)))
    return found


def test_a_rest_narrowed_to_nights_leaves_mornings_alone():
    profile = _profile(PEOPLE[:3], audit_policy={"min_rest_hours": 0, "max_consecutive_days": 7})
    rest = _request("min_rest", count=30, shifts=[NIGHT])

    alone = _gaps(generate_span(profile, SUNDAY, SATURDAY)["assignments"], PEOPLE[:3])
    rested = _gaps(generate_span(profile, SUNDAY, SATURDAY, requests=[rest])["assignments"],
                   PEOPLE[:3])

    assert min(gap for gap, night in alone if night) < 30
    assert min(gap for gap, night in rested if night) >= 30
    assert min(gap for gap, night in rested if not night) < 30


def test_no_more_than_two_nights_in_a_row():
    likes_nights = _request("prefer", employees=["דנה"], shifts=[NIGHT], hard=False, weight=5)
    limit = _request("max_consecutive", count=2, shifts=[NIGHT])
    profile = _profile(PEOPLE[:3])

    alone = generate_span(profile, SUNDAY, SATURDAY, requests=[likes_nights])
    limited = generate_span(profile, SUNDAY, SATURDAY, requests=[likes_nights, limit])

    assert _longest_run(alone["assignments"], "דנה", NIGHT) > 2
    assert _longest_run(limited["assignments"], "דנה", NIGHT) == 2


def test_a_run_counts_the_days_before_the_period():
    history = [{"employee": "דנה", "shift": MORNING, "date": day, "reason": "היסטוריה"}
               for day in ("2026-08-13", "2026-08-14", "2026-08-15")]
    profile = _profile(("דנה", "יוסי"), night=0, audit_policy={"max_consecutive_days": 10})
    away = [{"employee": "יוסי", "date": SUNDAY, "shift": MORNING, "available": False,
             "is_hard": True, "reason": "חופשה"}]
    run = _request("max_consecutive", employees=["דנה"], count=3)

    alone = generate_span(profile, SUNDAY, SUNDAY, history=history, availability=away)
    limited = generate_span(profile, SUNDAY, SUNDAY, history=history, availability=away,
                            requests=[run])

    assert [row["employee"] for row in alone["assignments"]] == ["דנה"]
    assert limited["assignments"] == []


def _weekends(requests):
    rows, profile = [], _profile(PEOPLE[:3])
    for week in range(4):
        start = datetime.date(2026, 8, 16) + datetime.timedelta(weeks=week)
        end = start + datetime.timedelta(days=6)
        rows += generate_span(profile, start.isoformat(), end.isoformat(),
                              already_scheduled=list(rows), requests=requests)["assignments"]
    counts = {name: 0 for name in PEOPLE[:3]}
    for row in rows:
        if datetime.date.fromisoformat(row["date"]).weekday() in (4, 5):
            counts[row["employee"]] += 1
    return max(counts.values()) - min(counts.values())


def test_weekends_are_spread_evenly_even_against_a_wish():
    likes_weekends = _request("prefer", employees=["דנה"], weekdays=["שישי", "שבת"],
                              hard=False, weight=1)
    balance = _request("balance", weekdays=["שישי", "שבת"], hard=False, weight=3)

    assert _weekends([likes_weekends]) > 2
    assert _weekends([likes_weekends, balance]) <= 1


def test_someone_new_works_only_beside_a_named_partner():
    company = _request("requires_with", employees=["נועה"], partners=["דנה"])
    result = generate_span(_profile(morning=2, night=2), SUNDAY, SATURDAY, requests=[company])

    alone = generate_span(_profile(morning=2, night=2), SUNDAY, SATURDAY)

    rows = result["assignments"]
    lonely = {(row["date"], row["shift"]) for row in alone["assignments"] if row["employee"] == "נועה"}
    assert lonely - {(row["date"], row["shift"]) for row in alone["assignments"]
                     if row["employee"] == "דנה"}
    with_noa = {(row["date"], row["shift"]) for row in rows if row["employee"] == "נועה"}
    with_dana = {(row["date"], row["shift"]) for row in rows if row["employee"] == "דנה"}
    assert with_noa and with_noa <= with_dana


class _Llm:
    def __init__(self, *answers):
        self.answers, self.payloads = list(answers), []

    def complete_json(self, system, user, schema=None, **kwargs):
        self.payloads.append(json.loads(user))
        return self.answers.pop(0)


def _answer(requests):
    return {"calls": [], "directives": [], "unresolved": [], "requests": requests,
            "timing": [{"source_id": "source-1", "kind": "none", "phrase": "", "starts_on": "",
                        "ends_on": "", "maybe_through": "", "question": ""}]}


def test_a_rest_policy_now_translates_and_code_builds_the_week():
    profile = _profile(rest_policy="מינימום 16 שעות מנוחה בין משמרות, ולא יותר משני לילות ברצף")
    rest = dict(_request("min_rest", count=16), source_id="source-1")
    run = dict(_request("max_consecutive", count=2, shifts=[NIGHT]), source_id="source-1")
    llm = _Llm(_answer([rest, run]))

    result = Scheduler(llm).generate_span(profile, SUNDAY, SATURDAY)

    assert result["metrics"]["engine"] == "hybrid"
    assert min(_rests(result["assignments"])) >= 16
    sent = llm.payloads[0]["sources"][0]
    assert sent["kind"] == "rest_policy" and sent["mode"] == "compile"


def test_the_translation_schema_carries_partners():
    llm = _Llm(_answer([dict(_request("requires_with", employees=["נועה"], partners=["דנה"]),
                             source_id="source-1")]))
    profile = _profile(employees=None)
    profile["employees"] = [{"name": name, **({"notes": "רק עם דנה"} if name == "נועה" else {})}
                            for name in PEOPLE]

    translated = DirectiveAgent(llm).translate(profile, SUNDAY, SATURDAY)

    assert translated["requests"][0]["partners"] == ["דנה"]


def test_native_daily_rule_and_officer_month_limit_apply_without_translation():
    profile = _profile(PEOPLE[:2])
    officer, regular = profile["employees"]
    officer["rank_group"] = "officer"
    profile["rules"] = [
        {"text": "אין לשבץ אדם פעמיים באותו יום", "priority": "hard"},
        {"text": "אין לשבץ קצינים ליותר מ-6 משמרות בחודש", "priority": "hard"},
    ]
    history = [{"employee": officer["name"], "shift": MORNING, "date": "2026-08-%02d" % day}
               for day in range(1, 7)]
    result = Scheduler(None).generate_span(profile, "2026-08-31", "2026-09-01", history=history)
    pairs = [(row["employee"], row["date"]) for row in result["assignments"]]
    assert len(pairs) == len(set(pairs))
    assert set(pairs) == {(regular["name"], "2026-08-31"), (regular["name"], "2026-09-01"),
                          (officer["name"], "2026-09-01")}


def test_daily_rule_rejects_two_mandatory_assignments_on_one_date():
    import pytest
    from app.common.errors import AgentError

    profile = _profile()
    profile["rules"] = [{"text": "אין לשבץ אדם פעמיים באותו יום", "priority": "hard"}]
    pins = [{"shift": shift, "employee": PEOPLE[0], "date": SUNDAY} for shift in (MORNING, NIGHT)]
    with pytest.raises(AgentError, match="שתי משמרות"):
        generate_span(profile, SUNDAY, SUNDAY, required_assignments=pins)


def test_rebuilding_a_week_reserves_officer_capacity_for_other_weeks():
    profile = _profile(PEOPLE[:1])
    officer = profile["employees"][0]
    officer["rank_group"] = "officer"
    profile["rules"] = [{"text": "אין לשבץ קצינים ליותר מ-2 משמרות בחודש", "priority": "hard"}]
    past = {"employee": officer["name"], "date": "2026-08-01", "shift": MORNING}
    future = dict(past, date="2026-08-28")
    result = generate_span(profile, SUNDAY, SATURDAY, history=[past], already_scheduled=[future])
    assert not result["assignments"]
    assert any("מכסת המשמרות החודשית" in note for note in result["notes"])


def test_1700_to_0100_uses_one_start_date_and_eight_hours():
    from app.bl.audit.roster import shift_hours

    profile = _profile(PEOPLE[:1])
    evening = dict(profile["shifts"][0], name="ערב", start_time="17:00", end_time="01:00")
    morning = dict(profile["shifts"][0], start_time="09:00", end_time="17:00")
    profile["shifts"] = [evening, morning]
    assert shift_hours(evening) == 8
    pins = [dict(employee=PEOPLE[0], shift="ערב", date=SUNDAY),
            dict(employee=PEOPLE[0], shift=MORNING, date="2026-08-17")]
    result = generate_span(profile, SUNDAY, "2026-08-17", required_assignments=[pins[0]])
    assert len(result["assignments"]) == 2
    result = generate_span(profile, SUNDAY, "2026-08-17", required_assignments=pins)
    assert {(r["date"], r["shift"]) for r in result["assignments"]} == {(p["date"], p["shift"]) for p in pins}
