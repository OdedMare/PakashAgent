"""`GET /api/schedule/stats`: the panel's numbers for a span and a person.

Pinned through the HTTP contract for the reason the overview's stats are: the
Pydantic models are what the browser receives, and a field `shift_stats`
grew that `ShiftStats` never declared would be dropped here in silence.

The arithmetic itself is `test_shift_stats.py`'s. These tests are about what
the route adds to it -- which rows of which periods reach that arithmetic.
"""

from app.common.sessions.sessions import ROLE_MEMBER
from tests.test_schedule_api import MORNING, _build_app, _client

WEEK_ONE = ("2026-08-16", "2026-08-22")
WEEK_TWO = ("2026-08-23", "2026-08-29")


def _two_weeks():
    """Dana on three mornings of the first week and one of the second,
    Yossi on one of each."""
    app, repo = _build_app([])
    client = _client(app)
    placed = {
        WEEK_ONE: [("דנה", "2026-08-16"), ("דנה", "2026-08-17"),
                   ("דנה", "2026-08-18"), ("יוסי", "2026-08-19")],
        WEEK_TWO: [("דנה", "2026-08-23"), ("יוסי", "2026-08-24")],
    }
    for (starts_on, ends_on), people in placed.items():
        schedule = client.post("/api/schedule/blank", json={
            "starts_on": starts_on, "ends_on": ends_on,
        }).json()
        for employee, date in people:
            response = client.post("/api/schedule/assign", json={
                "schedule_id": schedule["id"], "employee": employee,
                "shift_name": MORNING, "slot_date": date,
            })
            assert response.status_code == 200, response.text
    return client


def _stats(client, start, end, **params):
    response = client.get("/api/schedule/stats", params=dict(
        params, start=start, end=end,
    ))
    assert response.status_code == 200, response.text
    return response.json()


def _shifts(stats):
    return {row["employee"]: row["shifts"] for row in stats["by_employee"]}


def test_a_week_reports_that_weeks_shifts_per_person():
    stats = _stats(_two_weeks(), *WEEK_ONE)

    assert stats["total_shifts"] == 4
    assert _shifts(stats) == {"דנה": 3, "יוסי": 1}
    assert [row["employee"] for row in stats["by_employee"]] == ["דנה", "יוסי"]
    assert len(stats["by_day"]) == 7


def test_a_span_across_periods_adds_them_up():
    """A month is not a stored period, and neither is a fortnight."""
    stats = _stats(_two_weeks(), WEEK_ONE[0], WEEK_TWO[1])

    assert stats["total_shifts"] == 6
    assert _shifts(stats) == {"דנה": 4, "יוסי": 2}
    assert len(stats["by_day"]) == 14


def test_a_single_day_reports_only_that_day():
    stats = _stats(_two_weeks(), "2026-08-17", "2026-08-17")

    assert stats["total_shifts"] == 1
    assert _shifts(stats) == {"דנה": 1, "יוסי": 0}
    assert [row["date"] for row in stats["by_day"]] == ["2026-08-17"]
    # One seat that day, and it is filled: the other six days of the period
    # are not counted against a day that was asked about alone.
    assert stats["coverage"]["required"] == 1
    assert stats["coverage"]["percent"] == 100.0


def test_a_span_clipping_two_periods_counts_only_the_days_inside_it():
    stats = _stats(_two_weeks(), "2026-08-19", "2026-08-23")

    assert stats["total_shifts"] == 2
    assert _shifts(stats) == {"דנה": 1, "יוסי": 1}
    assert len(stats["by_day"]) == 5


def test_a_whole_period_reports_what_the_overview_reports_for_it():
    """The two are the same arithmetic over the same rows, so the default
    view and a filter that happens to match it cannot disagree."""
    client = _two_weeks()
    overview = client.get("/api/schedule/overview").json()
    period = overview["schedule"]

    stats = _stats(client, period["starts_on"], period["ends_on"])

    assert stats == overview["stats"]


def test_one_person_across_a_span():
    stats = _stats(_two_weeks(), WEEK_ONE[0], WEEK_TWO[1], employee="יוסי")

    assert stats["total_shifts"] == 2
    assert stats["people_working"] == 1
    assert _shifts(stats) == {"יוסי": 2}


def test_conflicts_are_the_spans_own_warnings():
    """Six of the first week's seven mornings have nobody on them once the
    span is cut to that week -- and each is printed under its calendar."""
    client = _two_weeks()
    week = client.get("/api/schedule/at", params={"day": WEEK_ONE[0]}).json()
    expected = len([
        row for row in week["warnings"] if row["severity"] == "warning"
    ])

    stats = _stats(client, *WEEK_ONE)

    assert expected and stats["conflicts"] == expected
    assert _stats(client, "2026-08-16", "2026-08-16")["conflicts"] < expected


def test_a_span_nothing_was_built_in_is_zeros_with_the_roster_present():
    stats = _stats(_two_weeks(), "2026-10-01", "2026-10-31")

    assert stats["total_shifts"] == 0
    assert stats["conflicts"] == 0
    assert _shifts(stats) == {"דנה": 0, "יוסי": 0}


def test_a_backwards_or_unreadable_span_is_refused_in_hebrew():
    client = _two_weeks()

    for start, end in (("2026-08-22", "2026-08-16"), ("אתמול", "2026-08-16")):
        response = client.get("/api/schedule/stats", params={
            "start": start, "end": end,
        })
        assert response.status_code >= 400
        assert "התאריכים" in response.text


def test_a_span_too_wide_to_audit_in_one_request_is_refused():
    response = _two_weeks().get("/api/schedule/stats", params={
        "start": "2026-01-01", "end": "2026-12-31",
    })

    assert response.status_code >= 400


def test_a_member_cannot_read_load_per_person():
    """Hours and shifts per colleague are the manager's view (D27)."""
    app, _ = _build_app([])
    member = _client(app, role=ROLE_MEMBER)

    response = member.get("/api/schedule/stats", params={
        "start": WEEK_ONE[0], "end": WEEK_ONE[1],
    })

    assert response.status_code in (401, 403)
