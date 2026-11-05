"""Continuity: a new week keeps the shape of the last two."""

import datetime

from app.bl.solver import generate_span
from app.bl.solver.continuity import level

START = "2026-09-06"  # a Sunday


def _day(days_before: int) -> str:
    return (datetime.date.fromisoformat(START) - datetime.timedelta(days=days_before)).isoformat()


def _profile(continuity=None):
    profile = {
        "workplace": {"name": "יחידה"},
        "employees": [{"name": "אבי"}, {"name": "בני"}],
        "shifts": [
            # Two posts at the same hours: rest and evenness cannot tell
            # one week's choice from another, only continuity can.
            {"name": "שער", "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
            {"name": "מגדל", "start_time": "07:00", "end_time": "15:00", "days": [],
             "staffing": [{"days": [], "headcount": 1, "required_roles": []}]},
        ],
    }
    # Two weeks every day in a row would otherwise stop the run on Sunday.
    profile["audit_policy"] = {"max_consecutive_days": 30}
    if continuity:
        profile["audit_policy"]["continuity"] = continuity
    return profile


def _two_weeks(gate="אבי", tower="בני"):
    return [{"employee": name, "shift": shift, "date": _day(age)}
            for age in range(1, 15) for name, shift in ((gate, "שער"), (tower, "מגדל"))]


def _held(result):
    return {(row["employee"], row["shift"]) for row in result["assignments"]}


def test_each_keeps_the_shift_they_held_the_last_two_weeks():
    for gate, tower in (("אבי", "בני"), ("בני", "אבי")):
        result = generate_span(_profile(), START, "2026-09-12", history=_two_weeks(gate, tower))

        assert _held(result) == {(gate, "שער"), (tower, "מגדל")}
        assert result["metrics"]["continuity_kept"] == result["metrics"]["continuity_rows"] == 14


def test_evenness_wins_over_the_pattern():
    """אבי held every night of the last two weeks and בני none: keeping the
    pattern would leave him on them, but the load moves to בני."""
    profile = _profile()
    profile["shifts"] = [{"name": "לילה", "start_time": "23:00", "end_time": "07:00", "days": [],
                          "staffing": [{"days": [], "headcount": 1, "required_roles": []}]}]
    history = [{"employee": "אבי", "shift": "לילה", "date": _day(age)} for age in range(1, 15)]
    history += [{"employee": name, "shift": "לילה", "date": _day(age)}
                for name, age in (("אבי", 21), ("בני", 22))]

    result = generate_span(profile, START, "2026-09-12", history=history)

    taken = [row["employee"] for row in result["assignments"]]
    assert taken.count("בני") >= 6


def test_the_policy_reads_off_low_or_high():
    assert level({}) == "low"
    assert level({"audit_policy": {"continuity": "off"}}) == "off"
    assert level({"audit_policy": {"continuity": "high"}}) == "high"
    assert level({"audit_policy": {"continuity": "always"}}) == "low"


def test_the_reward_stays_below_the_lightest_shift_of_evenness_and_any_rest():
    """Continuity only picks among schedules that are otherwise as good."""
    from app.bl.audit.roster import LOAD_WEIGHTS
    from app.bl.solver.continuity import REWARD, WEEKS
    from app.bl.solver.model import SHIFT_PEAK, SHIFT_SCALE, SHIFT_SPREAD

    lightest = round(SHIFT_SCALE * min(LOAD_WEIGHTS)) * (2 * SHIFT_SPREAD + SHIFT_PEAK)
    assert max(REWARD.values()) * WEEKS < lightest
