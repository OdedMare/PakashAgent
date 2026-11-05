"""The fairness ledger: who carried the load in the eight weeks before."""

import datetime

from app.bl.schedule_service.generation.history import AssignmentHistory
from app.bl.solver import generate_span
from app.bl.solver import ledger

START = "2026-09-06"  # a Sunday


def _day(days_before: int) -> str:
    return (datetime.date.fromisoformat(START) - datetime.timedelta(days=days_before)).isoformat()


def _nights_only(people=("אבי", "בני", "גדי"), weeks=None):
    profile = {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": name} for name in people],
        "shifts": [{"name": "לילה", "start_time": "23:00", "end_time": "07:00", "days": [],
                    "staffing": [{"days": [], "headcount": 1, "required_roles": []}]}],
    }
    if weeks is not None:
        profile["audit_policy"] = {"fairness_lookback_weeks": weeks}
    return profile


def _nights(name, ages):
    return [{"employee": name, "shift": "לילה", "date": _day(age)} for age in ages]


def _counts(assignments):
    counts = {}
    for row in assignments:
        counts[row["employee"]] = counts.get(row["employee"], 0) + 1
    return counts


def _heavy_month_ago():
    """Weeks three to eight: אבי took twelve nights, the others three each.
    The last two weeks (the fixed rows) are even."""
    history = _nights("אבי", range(20, 44, 2)) + _nights("בני", (21, 35, 49)) \
        + _nights("גדי", (23, 37, 51))
    for age in range(1, 13):
        history += _nights(("אבי", "בני", "גדי")[age % 3], (age,))
    return history


def test_a_month_old_excess_still_evens_out():
    result = generate_span(_nights_only(), START, _day(-5), history=_heavy_month_ago())

    counts = _counts(result["assignments"])
    assert sum(counts.values()) == 6
    assert counts.get("אבי", 0) == 0


def test_without_the_ledger_only_the_last_two_weeks_count():
    result = generate_span(_nights_only(weeks=0), START, _day(-5), history=_heavy_month_ago())

    assert _counts(result["assignments"]) == {"אבי": 2, "בני": 2, "גדי": 2}


def test_a_newcomer_is_not_owed_the_weeks_before_they_came():
    """אבי and בני took a night in turn for eight weeks; גדי came this week.
    Counted from zero, גדי would be handed every night of the span."""
    history = _nights("אבי", range(1, 57, 2)) + _nights("בני", range(2, 57, 2))

    result = generate_span(_nights_only(), START, _day(-5), history=history)

    assert _counts(result["assignments"]) == {"אבי": 2, "בני": 2, "גדי": 2}


def test_an_older_week_counts_half():
    assert ledger.share(28) == 1.0
    assert ledger.share(29) == ledger.OLD_SHARE


def test_absent_weeks_are_filled_at_the_teams_rate():
    rows = [{"employee": "אבי", "age": age, "load": 1.0, "night": False} for age in (20, 27)]
    rows += [{"employee": name, "age": 3, "load": 1.0, "night": False, "recent": True}
             for name in ("אבי", "בני")]
    carried = ledger.carried(rows, {"אבי": 27, "בני": 3}, {1, 2, 3, 4}, ["אבי", "בני"],
                             weeks=4, measure=lambda row: 10)

    # Forty in five person-weeks: אבי was there for four weeks, בני for one.
    # The recent rows are the evenness's own; only the older load and the
    # weeks בני was not there are carried.
    rate = 40 / 5
    assert carried == {"אבי": 20, "בני": round(3 * rate)}


def test_a_week_with_no_schedule_is_not_filled():
    rows = [{"employee": "אבי", "age": 3, "load": 1.0, "night": False, "recent": True}]
    carried = ledger.carried(rows, {"אבי": 3}, {1}, ["אבי", "בני"], weeks=8,
                             measure=lambda row: 10)

    # Only week one had a schedule: בני is filled for it alone.
    assert carried == {"בני": 10}


def test_the_window_is_set_by_the_policy_and_capped():
    assert ledger.lookback_weeks({}) == 8
    assert ledger.lookback_weeks({"audit_policy": {"fairness_lookback_weeks": 0}}) == 0
    assert ledger.lookback_weeks({"audit_policy": {"fairness_lookback_weeks": 40}}) == ledger.MAX_WEEKS


class _Periods:
    """Ten weekly periods of forty rows each, newest first."""

    def __init__(self):
        sunday = datetime.date.fromisoformat(START)
        self.periods = [{"id": str(week), "starts_on": sunday - datetime.timedelta(weeks=week),
                         "ends_on": sunday - datetime.timedelta(weeks=week, days=-6)}
                        for week in range(1, 11)]

    def list_schedules(self, team_id):
        return self.periods

    def assignments(self, period_id, team_id):
        first = next(p["starts_on"] for p in self.periods if p["id"] == period_id)
        return [{"employee": "עובד %02d" % number, "shift": "לילה",
                 "date": first + datetime.timedelta(days=number % 7)} for number in range(40)]


def test_history_is_read_back_as_far_as_the_ledger_reaches():
    rows = AssignmentHistory(_Periods()).before("team", START)

    oldest = min(row["date"] for row in rows)
    assert len(rows) > 300
    assert oldest >= _day(ledger.MAX_WEEKS * 7)
    assert oldest <= _day(8 * 7)
