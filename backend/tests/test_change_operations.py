"""What a proposal is allowed to carry, and what it must not swallow.

`bl/changes.py` bounds the model's operations to targets that exist. That
bound was doing two things it should not: it read a blank shift as "no
shift" rather than "that day" — throwing away *"תוריד את דנה מיום חמישי"*,
the most ordinary removal the product has — and it dropped whatever it could
not place **silently**, leaving the manager a confident sentence ("העברתי את
דנה"), no confirm button, and a schedule that had not moved.

So what is asserted here is that a change either lands, or is asked about, or
is reported. Never that it quietly does none of the three.
"""

from app.bl.changes import ChangeAgent, OP_ASSIGN, OP_REMOVE, OP_SWAP

MORNING = "בוקר"
EVENING = "ערב"

PROFILE = {
    "workplace": {"name": "מוקד"},
    "employees": [
        {"name": "דנה", "eligible_shifts": [MORNING, EVENING]},
        {"name": "יוסי", "eligible_shifts": [MORNING, EVENING]},
    ],
    "shifts": [
        {"name": MORNING, "start_time": "07:00", "end_time": "15:00"},
        {"name": EVENING, "start_time": "15:00", "end_time": "23:00"},
    ],
    "rules": [],
}

SCHEDULE = {
    "id": "sched-1",
    "starts_on": "2026-08-17",
    "ends_on": "2026-08-23",
    "slots": [
        {"shift_name": MORNING, "slot_date": "2026-08-20", "headcount": 1},
        {"shift_name": EVENING, "slot_date": "2026-08-20", "headcount": 1},
    ],
    "assignments": [
        {"employee": "דנה", "shift": MORNING, "date": "2026-08-20",
         "reason": "שיבוץ מקורי"},
    ],
}


class _ScriptedLlm:
    def __init__(self, answer):
        self._answer = answer

    def complete_json(self, system, user, schema=None, flow=""):
        return self._answer


def _change(operations=None, reply="הצעה", **extra):
    answer = {
        "reply": reply,
        "needs_reason": False,
        "needs_input": False,
        "agent_reason": "נבדקו החלופות",
        "operations": operations or [],
        "constraints": [],
        "profile_operations": [],
    }
    answer.update(extra)
    return answer


def _propose(answer, request="תוריד את דנה", reason="מחלה"):
    return ChangeAgent(_ScriptedLlm(answer)).propose(
        PROFILE, SCHEDULE, request, stated_reason=reason,
    )


def test_a_removal_naming_only_a_day_resolves_to_the_shift_they_are_on():
    """"תוריד את דנה מיום חמישי" names a person and a date, and that is it.

    An empty shift means the whole day — the convention `_match` has always
    read — and bounding it against the slot grid threw every one of these
    away, because `("", date)` is not a slot and never will be.
    """
    proposal = _propose(_change([{
        "action": OP_REMOVE, "employee": "דנה", "shift": "",
        "date": "2026-08-20", "reason": "חולה",
    }]))

    assert proposal["needs_input"] is False
    assert [(row["action"], row["employee"], row["shift"])
            for row in proposal["operations"]] == [
        (OP_REMOVE, "דנה", MORNING),
    ]


def test_a_removal_naming_only_a_day_asks_when_the_day_holds_two_shifts():
    """Two rows that day is the one case that is a question, not a report."""
    schedule = dict(SCHEDULE, assignments=[
        SCHEDULE["assignments"][0],
        {"employee": "דנה", "shift": EVENING, "date": "2026-08-20",
         "reason": "שיבוץ מקורי"},
    ])
    agent = ChangeAgent(_ScriptedLlm(_change([{
        "action": OP_REMOVE, "employee": "דנה", "shift": "",
        "date": "2026-08-20", "reason": "חולה",
    }])))

    proposal = agent.propose(
        PROFILE, schedule, "תוריד את דנה מחמישי", stated_reason="מחלה",
    )

    assert proposal["needs_input"] is True
    assert proposal["operations"] == []
    # The real candidates, so answering costs one tap rather than a sentence.
    assert MORNING in proposal["reply"] and EVENING in proposal["reply"]
    # And the request is held, so the answer resumes it rather than
    # replacing it.
    assert proposal["pending_request"] == "תוריד את דנה מחמישי"


def test_an_assignment_naming_only_a_day_takes_the_one_shift_that_runs():
    """One shift that day is not a guess — there was nothing else meant."""
    schedule = dict(SCHEDULE, slots=[
        {"shift_name": EVENING, "slot_date": "2026-08-21", "headcount": 1},
    ])
    agent = ChangeAgent(_ScriptedLlm(_change([{
        "action": OP_ASSIGN, "employee": "יוסי", "shift": "",
        "date": "2026-08-21", "reason": "מחליף את דנה",
    }])))

    proposal = agent.propose(
        PROFILE, schedule, "תשבץ את יוסי בשישי", stated_reason="דנה חולה",
    )

    assert [row["shift"] for row in proposal["operations"]] == [EVENING]


def test_a_target_that_is_not_in_the_period_is_reported_not_swallowed():
    """The bug this file exists for: a change that went nowhere, silently.

    The model's `reply` describes the move as done. Leaving that standing in
    front of an empty proposal is what "the agent does not really change
    shifts" looked like from the manager's chair.
    """
    proposal = _propose(_change(
        [{
            "action": OP_ASSIGN, "employee": "יוסי", "shift": MORNING,
            "date": "2026-09-30", "reason": "מחליף את דנה",
        }],
        reply="שיבצתי את יוסי לבוקר.",
    ))

    assert proposal["operations"] == []
    assert "שיבצתי" not in proposal["reply"]
    assert "2026-09-30" in proposal["reply"]


def test_a_removal_of_somebody_who_is_not_there_says_so():
    proposal = _propose(_change(
        [{
            "action": OP_REMOVE, "employee": "יוסי", "shift": "",
            "date": "2026-08-20", "reason": "חולה",
        }],
        reply="הורדתי את יוסי.",
    ))

    assert proposal["operations"] == []
    assert "יוסי" in proposal["reply"]
    assert "הורדתי" not in proposal["reply"]


def test_what_can_be_done_is_still_proposed_when_something_else_cannot():
    """A request that mostly works is carried out, not held behind one gap.

    Putting the whole proposal behind a question about the one operation
    that failed would make a four-move change all-or-nothing, which is
    neither what the manager asked for nor what the gate is for.
    """
    proposal = _propose(_change([
        {"action": OP_REMOVE, "employee": "דנה", "shift": MORNING,
         "date": "2026-08-20", "reason": "חולה"},
        {"action": OP_ASSIGN, "employee": "יוסי", "shift": MORNING,
         "date": "2026-09-30", "reason": "מחליף"},
    ]))

    assert [row["employee"] for row in proposal["operations"]] == ["דנה"]
    assert proposal["needs_input"] is False


def test_the_reason_question_survives_an_operation_that_went_nowhere():
    """One question at a time, and the older gate keeps its turn.

    A proposal held for a missing reason has emptied its operations too, so
    the drop report must not step in front of the question the manager is
    already being asked (D8).
    """
    proposal = ChangeAgent(_ScriptedLlm(_change(
        [{
            "action": OP_REMOVE, "employee": "דנה", "shift": MORNING,
            "date": "2026-09-30", "reason": "",
        }],
        reply="למה דנה לא מגיעה?", needs_reason=True,
    ))).propose(PROFILE, SCHEDULE, "תוריד את דנה")

    assert proposal["needs_reason"] is True
    assert proposal["reply"] == "למה דנה לא מגיעה?"


def test_a_swap_reads_each_side_against_what_that_person_is_on():
    schedule = dict(SCHEDULE, assignments=[
        SCHEDULE["assignments"][0],
        {"employee": "יוסי", "shift": EVENING, "date": "2026-08-20",
         "reason": "שיבוץ מקורי"},
    ])
    agent = ChangeAgent(_ScriptedLlm(_change([{
        "action": OP_SWAP, "employee": "דנה", "shift": "",
        "date": "2026-08-20", "with_employee": "יוסי",
        "with_shift": "", "with_date": "2026-08-20", "reason": "החלפה",
    }])))

    proposal = agent.propose(
        PROFILE, schedule, "תחליף בין דנה ליוסי", stated_reason="בקשה שלהם",
    )

    operation = proposal["operations"][0]
    assert operation["shift"] == MORNING
    assert operation["with_shift"] == EVENING


def test_a_schedule_with_no_stored_grid_can_still_have_a_row_removed():
    """An imported or older period has assignments and no slots.

    Bailing on an empty grid meant every operation was dropped before it was
    looked at, so the agent could not touch such a period at all.
    """
    schedule = dict(SCHEDULE, slots=[])
    agent = ChangeAgent(_ScriptedLlm(_change([{
        "action": OP_REMOVE, "employee": "דנה", "shift": MORNING,
        "date": "2026-08-20", "reason": "חולה",
    }])))

    proposal = agent.propose(
        PROFILE, schedule, "תוריד את דנה", stated_reason="מחלה",
    )

    assert [row["employee"] for row in proposal["operations"]] == ["דנה"]
