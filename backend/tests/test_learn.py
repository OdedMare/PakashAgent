"""Learning patterns and candidate rules from a pile of past schedules.

Split the way the module is: `observe()` is arithmetic and is tested against
exact numbers with no model at all, and `RuleLearner` is tested for what it
*refuses* to pass through — because the value of the confirm step (D7) is
entirely in the bounding, not in the model's wording.
"""

import json

import pytest

from app.bl.learn import RuleLearner, observe
from app.common.errors import AgentError

MORNING = "בוקר"
EVENING = "צהריים"
ON_CALL = "כונן לילה"
PROFILE = {
    "shifts": [{"name": MORNING}, {"name": EVENING}, {"name": ON_CALL}],
    "employees": [{"name": "יערה"}, {"name": "מאור"}],
}


class _ScriptedLlm:
    """Returns the next scripted answer and records what it was asked."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.calls = []

    def complete_json(self, system, user, schema=None):
        self.calls.append({"system": system, "user": user})
        if not self._answers:
            raise AssertionError("model called more times than scripted")
        return self._answers.pop(0)


def _rows(employee, shift, dates):
    return [
        {"employee": employee, "shift": shift, "date": date} for date in dates
    ]


# 2026-06-01 is a Monday, so these run Mon..Sun.
WEEK = ["2026-06-0%d" % day for day in range(1, 8)]


# -- observe(): arithmetic, no model --------------------------------------

def test_counts_a_persons_assignments():
    found = observe(_rows("יערה", MORNING, WEEK), profile=PROFILE)
    person = found["people"][0]
    assert person["employee"] == "יערה"
    assert person["assignments"] == 7


def test_identifies_a_shift_someone_always_works():
    found = observe(_rows("יערה", MORNING, WEEK), profile=PROFILE)
    assert found["people"][0]["always"] == [MORNING]


def test_identifies_a_shift_someone_never_works():
    """The absence is the signal, so it must survive being a zero.

    `צהריים` appears nowhere in יערה's rows; counting only what she worked
    would make "never works evenings" unrepresentable.
    """
    found = observe(_rows("יערה", MORNING, WEEK), profile=PROFILE)
    assert EVENING in found["people"][0]["never"]
    assert ON_CALL in found["people"][0]["never"]


def test_a_single_exception_does_not_erase_a_pattern():
    """A real rota has one covered evening in it; 0.9 not 1.0."""
    rows = _rows("יערה", MORNING, WEEK * 3) + _rows("יערה", EVENING, ["2026-06-10"])
    found = observe(rows, profile=PROFILE)
    assert found["people"][0]["always"] == [MORNING]


def test_too_few_appearances_supports_no_claim():
    """Three shifts is not a pattern, and must not be presented as one."""
    found = observe(_rows("מאור", MORNING, WEEK[:3]), profile=PROFILE)
    person = found["people"][0]
    assert person["enough_data"] is False
    assert person["always"] == []
    assert person["never"] == []


def test_splits_by_weekday():
    found = observe(_rows("יערה", MORNING, WEEK), profile=PROFILE)
    assert found["people"][0]["by_weekday"]["שבת"] == 1


def test_reports_a_weekday_the_files_never_covered():
    """The ambiguous case: closed, or simply not in these sheets."""
    found = observe(_rows("יערה", MORNING, WEEK[:5]), profile=PROFILE)
    assert "שבת" in found["coverage"]["weekdays_never_seen"]
    assert "יום ראשון" in found["coverage"]["weekdays_never_seen"]


def test_reports_the_span_the_history_covers():
    found = observe(_rows("יערה", MORNING, WEEK), profile=PROFILE)
    assert found["periods"]["starts_on"] == "2026-06-01"
    assert found["periods"]["ends_on"] == "2026-06-07"
    assert found["periods"]["days"] == 7


def test_a_written_constraint_is_kept_apart_from_inferences():
    """A `לא זמין` cell is evidence of a different quality entirely."""
    found = observe(
        _rows("יערה", MORNING, WEEK),
        unavailability=[{
            "employee": "מאור", "date": "2026-06-03",
            "shift": EVENING, "reason": "לא זמין",
        }],
        profile=PROFILE,
    )
    assert len(found["stated_unavailability"]) == 1
    assert found["stated_unavailability"][0]["employee"] == "מאור"


def test_unreadable_rows_are_skipped_not_fatal():
    """Imported data is arbitrary; a bad row must not sink the import."""
    rows = [{"employee": "", "shift": MORNING, "date": "2026-06-01"},
            {"employee": "יערה", "shift": MORNING, "date": "not-a-date"},
            {"employee": "יערה", "shift": MORNING, "date": "2026-06-01"}]
    found = observe(rows, profile=PROFILE)
    assert found["totals"]["assignments"] == 3
    assert len(found["people"]) == 1


# -- RuleLearner: what it refuses to pass through --------------------------

def _learner(rules, notes=None):
    return _ScriptedLlm([{"rules": rules, "notes": notes or []}])


def test_a_candidate_is_never_approved_by_being_proposed():
    """D7: the manager's approval is the only thing that makes a rule real."""
    llm = _learner([{
        "text": "יערה עובדת רק בקרים", "kind": "soft",
        "evidence": "7 מתוך 7", "confidence": "high",
    }])
    found = RuleLearner(llm).propose(
        observe(_rows("יערה", MORNING, WEEK), profile=PROFILE), PROFILE
    )
    assert found["rules"][0]["approved"] is False


def test_a_rule_without_evidence_is_dropped():
    """A claim the manager cannot check is one they cannot approve."""
    llm = _learner([{
        "text": "יערה עובדת רק בקרים", "kind": "soft",
        "evidence": "", "confidence": "high",
    }])
    found = RuleLearner(llm).propose(
        observe(_rows("יערה", MORNING, WEEK), profile=PROFILE), PROFILE
    )
    assert found["rules"] == []


def test_anything_but_an_explicit_hard_is_soft():
    """D1 makes a hard rule loud; an invented one nags about nothing."""
    llm = _learner([{
        "text": "כלל", "kind": "critical",
        "evidence": "7 מתוך 7", "confidence": "high",
    }])
    found = RuleLearner(llm).propose(
        observe(_rows("יערה", MORNING, WEEK), profile=PROFILE), PROFILE
    )
    assert found["rules"][0]["kind"] == "soft"


def test_an_unrecognised_confidence_becomes_low():
    llm = _learner([{
        "text": "כלל", "kind": "soft",
        "evidence": "7 מתוך 7", "confidence": "certain",
    }])
    found = RuleLearner(llm).propose(
        observe(_rows("יערה", MORNING, WEEK), profile=PROFILE), PROFILE
    )
    assert found["rules"][0]["confidence"] == "low"


def test_no_history_means_no_model_call_at_all():
    """Nothing to learn from is not a question worth asking a model."""
    llm = _ScriptedLlm([])
    found = RuleLearner(llm).propose(observe([], profile=PROFILE), PROFILE)
    assert found == {"rules": [], "notes": []}
    assert llm.calls == []


def test_the_counts_reach_the_model_as_facts():
    """D3: the model is handed the arithmetic, never asked to do it."""
    llm = _learner([])
    RuleLearner(llm).propose(
        observe(_rows("יערה", MORNING, WEEK), profile=PROFILE), PROFILE
    )
    payload = json.loads(llm.calls[0]["user"])
    assert payload["observations"]["people"][0]["assignments"] == 7


def test_a_malformed_reply_is_refused_in_hebrew():
    llm = _ScriptedLlm(["not a dict"])
    with pytest.raises(AgentError):
        RuleLearner(llm).propose(
            observe(_rows("יערה", MORNING, WEEK), profile=PROFILE), PROFILE
        )
