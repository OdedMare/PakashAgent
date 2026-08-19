"""Learning patterns and candidate rules from a pile of past schedules.

Split the way the module is: `observe()` is arithmetic and is tested against
exact numbers with no model at all, and `RuleLearner` is tested for what it
*refuses* to pass through — because the value of the confirm step (D7) is
entirely in the bounding, not in the model's wording.
"""

import json

import pytest

from app.bl.learn import RuleLearner, observe, observe_corrections
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


# --- learning from the manager's own corrections ----------------------------
#
# The other source, and the stronger one. An uploaded file shows what the
# workplace *did*; the change log shows what the manager **decided** and why
# (D8 guaranteed the reason would be there). These tests hold the counting to
# exact numbers, exactly as the `observe()` tests above do, and hold the
# learner to what it refuses to pass through.

def _change(action, employee, shift, date, reason="", replaced=""):
    return {
        "action": action,
        "employee": employee,
        "replaced_employee": replaced,
        "shift_name": shift,
        "slot_date": date,
        "reason": reason,
    }


def test_a_correction_repeated_is_counted_with_its_reasons():
    """The tally is keyed on person, shift and weekday — never the date.

    A rule is about Fridays, not about the 3rd of March, so three Fridays
    must collapse into one candidate rather than three."""
    # 2026-03-06, 03-13 and 03-20 are all Fridays.
    changes = [
        _change("moved", "מאור", EVENING, "2026-03-06", "לימודים"),
        _change("moved", "מאור", EVENING, "2026-03-13", "לימודים"),
        _change("moved", "מאור", EVENING, "2026-03-20", "יש לו קורס"),
    ]

    found = observe_corrections(changes)

    assert len(found["repeated"]) == 1
    entry = found["repeated"][0]
    assert entry["employee"] == "מאור"
    assert entry["count"] == 3
    assert entry["weekday"] == "יום שישי"
    # Reasons are collected verbatim and de-duplicated, never summarised:
    # deciding two sentences mean the same thing is a language job.
    assert entry["reasons"] == ["לימודים", "יש לו קורס"]
    assert entry["first_seen"] == "2026-03-06"
    assert entry["last_seen"] == "2026-03-20"


def test_a_single_correction_is_withheld_but_still_counted():
    """One correction is not a pattern; it is a Tuesday.

    Reported as a number rather than dropped, so the model can say "not
    enough yet" instead of inventing a reason for the silence."""
    changes = [_change("moved", "מאור", EVENING, "2026-03-06", "מחלה")]

    found = observe_corrections(changes)

    assert found["repeated"] == []
    assert found["single_corrections"] == 1
    assert found["totals"]["corrections"] == 1


def test_filling_an_empty_cell_is_not_a_correction():
    """`assigned` takes nothing away from anybody (D18), so it corrects
    nothing. Counting it would turn ordinary manual scheduling into evidence
    of a rule the manager never applied."""
    changes = [
        _change("assigned", "מאור", EVENING, "2026-03-06"),
        _change("assigned", "מאור", EVENING, "2026-03-13"),
        _change("published", "", "", "2026-03-06"),
        _change("generated", "", "", "2026-03-06"),
    ]

    found = observe_corrections(changes)

    assert found["repeated"] == []
    assert found["totals"]["corrections"] == 0


def test_a_swap_is_counted_against_whoever_was_taken_off():
    """The correction is about the person removed, not their replacement.

    That person was the *solution*, and a rule written about them would say
    the opposite of what happened."""
    changes = [
        _change(
            "swapped", "יערה", EVENING, "2026-03-06",
            reason="מאור לא יכול", replaced="מאור",
        ),
        _change(
            "swapped", "יערה", EVENING, "2026-03-13",
            reason="מאור לא יכול", replaced="מאור",
        ),
    ]

    found = observe_corrections(changes)

    assert len(found["repeated"]) == 1
    assert found["repeated"][0]["employee"] == "מאור"


def test_the_most_corrected_combination_comes_first():
    """The manager reads these in order, so the strongest evidence leads."""
    changes = [
        _change("moved", "מאור", EVENING, "2026-03-06", "לימודים"),
        _change("moved", "מאור", EVENING, "2026-03-13", "לימודים"),
        _change("moved", "מאור", EVENING, "2026-03-20", "לימודים"),
        _change("removed", "יערה", MORNING, "2026-03-02", "מילואים"),
        _change("removed", "יערה", MORNING, "2026-03-09", "מילואים"),
    ]

    found = observe_corrections(changes)

    assert [entry["count"] for entry in found["repeated"]] == [3, 2]
    assert found["repeated"][0]["employee"] == "מאור"


def test_nothing_repeated_costs_no_model_call():
    """The common case is answerable in arithmetic, and a round trip to be
    told there is nothing yet would cost a call on every screen."""
    llm = _ScriptedLlm([])
    learner = RuleLearner(llm)

    result = learner.propose_from_corrections(
        observe_corrections(
            [_change("moved", "מאור", EVENING, "2026-03-06", "מחלה")]
        ),
        PROFILE,
    )

    assert result == {"rules": [], "notes": []}
    assert llm.calls == []


def test_a_candidate_from_corrections_is_never_approved():
    """The whole point of D7: a rule becomes real by being chosen, never by
    having been proposed — and the model saying so does not change that."""
    llm = _ScriptedLlm([{
        "rules": [{
            "text": "מאור לא עובד ערבי שישי",
            "kind": "hard",
            "evidence": "הועבר 3 פעמים, הסיבה שנרשמה: לימודים",
            "confidence": "high",
            "approved": True,
        }],
        "notes": [],
    }])
    learner = RuleLearner(llm)
    changes = [
        _change("moved", "מאור", EVENING, "2026-03-06", "לימודים"),
        _change("moved", "מאור", EVENING, "2026-03-13", "לימודים"),
    ]

    result = learner.propose_from_corrections(
        observe_corrections(changes), PROFILE
    )

    assert result["rules"][0]["approved"] is False


def test_a_candidate_without_evidence_is_dropped():
    """A rule the manager cannot check is one they cannot meaningfully
    approve, which would make the confirm step theatre."""
    llm = _ScriptedLlm([{
        "rules": [
            {"text": "מאור לא עובד ערבי שישי", "kind": "soft",
             "evidence": "", "confidence": "high"},
            {"text": "", "kind": "soft",
             "evidence": "הועבר 3 פעמים", "confidence": "high"},
        ],
        "notes": [],
    }])
    learner = RuleLearner(llm)
    changes = [
        _change("moved", "מאור", EVENING, "2026-03-06", "לימודים"),
        _change("moved", "מאור", EVENING, "2026-03-13", "לימודים"),
    ]

    result = learner.propose_from_corrections(
        observe_corrections(changes), PROFILE
    )

    assert result["rules"] == []


def test_anything_but_an_explicit_hard_is_soft():
    """D1 makes a hard rule a strong instruction plus a loud warning, so an
    invented one nags the manager about a rule they never stated."""
    llm = _ScriptedLlm([{
        "rules": [{
            "text": "מאור מעדיף בקרים",
            "kind": "probably-hard",
            "evidence": "הועבר פעמיים",
            "confidence": "medium",
        }],
        "notes": [],
    }])
    learner = RuleLearner(llm)
    changes = [
        _change("moved", "מאור", EVENING, "2026-03-06", "לימודים"),
        _change("moved", "מאור", EVENING, "2026-03-13", "לימודים"),
    ]

    result = learner.propose_from_corrections(
        observe_corrections(changes), PROFILE
    )

    assert result["rules"][0]["kind"] == "soft"


def test_the_corrections_reach_the_model_as_counts():
    """The model is handed the tally, never asked to compute one: arithmetic
    over a roster is what it gets subtly wrong (D3)."""
    llm = _ScriptedLlm([{"rules": [], "notes": []}])
    learner = RuleLearner(llm)
    changes = [
        _change("moved", "מאור", EVENING, "2026-03-06", "לימודים"),
        _change("moved", "מאור", EVENING, "2026-03-13", "לימודים"),
    ]

    learner.propose_from_corrections(observe_corrections(changes), PROFILE)

    sent = json.loads(llm.calls[0]["user"])
    assert sent["corrections"]["repeated"][0]["count"] == 2
    # And the manager's own words travel with it, because they are what makes
    # the candidate checkable.
    assert "לימודים" in sent["corrections"]["repeated"][0]["reasons"]


def test_a_bad_model_answer_is_refused():
    llm = _ScriptedLlm(["not a dict"])
    learner = RuleLearner(llm)
    changes = [
        _change("moved", "מאור", EVENING, "2026-03-06", "לימודים"),
        _change("moved", "מאור", EVENING, "2026-03-13", "לימודים"),
    ]

    with pytest.raises(AgentError):
        learner.propose_from_corrections(
            observe_corrections(changes), PROFILE
        )
