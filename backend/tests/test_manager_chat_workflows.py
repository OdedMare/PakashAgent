"""Whole-day coverage, conversational approval and compound manager actions."""

import copy
import json

import pytest

from app.bl.audit import shift_stats
from app.bl.scheduler import effective_availability
from app.common.errors.errors import ConflictError
from tests.test_manager_chat import TEAM, MORNING, converse, setup, sickness, turn

EVENING = "ערב"


def two_shifts(repo):
    profile = repo.profiles[TEAM]
    profile["shifts"].append(dict(name=EVENING, start_time="15:00", end_time="23:00",
                                days=[], staffing=[dict(days=[], headcount=1, required_roles=[])]))
    profile["employees"][1]["eligible_shifts"].append(EVENING)
    schedule_id = next(iter(repo.schedules))
    repo.slots[schedule_id] += [dict(shift_name=row["name"], slot_date="2026-10-06",
        start_time=row["start_time"], end_time=row["end_time"], headcount=1,
        required_roles=[], id=repo._id("slot"), team_id=TEAM) for row in profile["shifts"]]


def generated(rows):
    return dict(assignments=[dict(employee=name, shift=shift, date="2026-10-06", reason="זמין ומוסמך")
                             for name, shift in rows], notes=[], summary="כל היום שובץ")


def test_whole_day_repairs_a_morning_only_answer_and_checks_evening():
    proposal = turn("generate")
    proposal.update(starts_on="2026-10-06", ends_on="2026-10-06")
    repo, llm, service, chat_id, _ = setup([proposal, generated([("דנה", MORNING)]),
                                         generated([("דנה", MORNING), ("יוסי", EVENING)])])
    two_shifts(repo)
    message = converse(service, repo, chat_id, "", "תשבץ את יום שלישי")
    assert message["status"] == "pending", message["content"]
    coverage = message["payload"]["plan"]["coverage"]
    assert coverage["complete"]
    assert {row["shift"] for row in coverage["slots"]} == {MORNING, EVENING}
    assert len(llm.calls) == 3
    assert len(repo.schedules) == 1  # Preview writes no period.


def test_unrepaired_day_is_visible_as_partial_and_gap_is_not_an_exception():
    proposal = turn("generate")
    proposal.update(starts_on="2026-10-06", ends_on="2026-10-06")
    response = generated([("דנה", MORNING)])
    repo, _, service, chat_id, _ = setup([proposal, response, response])
    two_shifts(repo)
    message = converse(service, repo, chat_id, "", "תשבץ את היום")
    assert "תוכנית חלקית" in message["content"] and EVENING in message["content"]
    assert not message["payload"]["plan"]["coverage"]["complete"]
    service.apply(TEAM, "manager-a", chat_id, message["id"])


def test_conversation_approval_uses_saved_plan_without_model_and_is_idempotent():
    repo, llm, service, chat_id, schedule_id = setup([sickness()])
    message = converse(service, repo, chat_id, schedule_id)
    request = dict(content="כן, תעשה", request_id="approval-1", approval_message_id=message["id"])
    assert service.start_turn(TEAM, "manager-a", chat_id, request) is None
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "יוסי"
    assert repo.get_chat(TEAM, "manager-a", chat_id)["messages"][-1]["payload"]["receipt"]
    changes = len(repo.changes)
    service.start_turn(TEAM, "manager-a", chat_id, request)
    assert len(repo.changes) == changes and len(llm.calls) == 1


def test_yes_answering_a_question_and_stale_text_approval_cannot_write():
    question = turn()
    question["question"] = dict(question="לאיזה יום?", recommendation="", why="",
                                options=[dict(label="שני", answer="יום שני")])
    repo, _, service, chat_id, schedule_id = setup([question, turn()])
    converse(service, repo, chat_id, schedule_id, "תחליף את דנה")
    converse(service, repo, chat_id, schedule_id, "כן", "clarification")
    assert not repo.changes
    with pytest.raises(ConflictError):
        service.start_turn(TEAM, "manager-a", chat_id, dict(content="כן", request_id="bad-approval",
                                                          approval_message_id="missing"))


def test_text_approval_preserves_exception_and_stale_state_guards():
    proposal = sickness()
    proposal["exceptions"] = ["חריגה מפורשת"]
    repo, _, service, chat_id, schedule_id = setup([proposal])
    message = converse(service, repo, chat_id, schedule_id)
    with pytest.raises(ConflictError, match="במפורש"):
        service.start_turn(TEAM, "manager-a", chat_id, dict(content="כן תעשה", request_id="exception",
                                                          approval_message_id=message["id"]))
    repo.set_availability(TEAM, "יוסי", "2026-10-05", reason="חופש")
    with pytest.raises(ConflictError, match="השתנו"):
        service.apply(TEAM, "manager-a", chat_id, message["id"], True)


def test_retirement_removes_future_work_across_periods_and_keeps_history():
    proposal = turn("retire", employee="דנה", effective_date="2026-10-05")
    repo, _, service, chat_id, schedule_id = setup([proposal])
    future = repo.create_schedule(TEAM, "2026-10-11", "2026-10-17")
    slot = repo.replace_slots(future["id"], TEAM, [dict(shift_name=MORNING, slot_date="2026-10-12")])[0]
    repo.add_assignment(future["id"], TEAM, slot["id"], "דנה", "שיבוץ עתידי")
    message = converse(service, repo, chat_id, schedule_id, "דנה התפטרה החל מיום שני")
    assert len(message["payload"]["plan"]["operations"]) == 2
    assert not repo.profiles[TEAM]["employees"][0].get("inactive_from")
    service.apply(TEAM, "manager-a", chat_id, message["id"])
    assert not repo.assignments(schedule_id, TEAM) and not repo.assignments(future["id"], TEAM)
    assert repo.profiles[TEAM]["employees"][0]["inactive_from"] == "2026-10-05"
    facts = effective_availability(repo.profiles[TEAM], [], "2026-10-04", "2026-10-06")
    assert {row["date"] for row in facts if row.get("source") == "retirement"} == {"2026-10-05", "2026-10-06"}


def structure_proposal(repo):
    shifts = [dict(name=name, start_time=start, end_time=end, days=[],
                   staffing=[dict(days=[], headcount=1, required_roles=[])])
              for name, start, end in [("יום", "12:00", "00:00"), ("לילה", "00:00", "12:00")]]
    people = [dict(row, eligible_shifts=["יום", "לילה"]) for row in repo.profiles[TEAM]["employees"]]
    result = turn("restructure")
    result.update(profile_patch_json=json.dumps(dict(shifts=shifts, employees=people)),
                  starts_on="2026-10-06", ends_on="2026-10-06")
    return result


@pytest.mark.parametrize("fail", [False, True])
def test_structure_migrates_profile_and_grid_atomically_preserving_other_assignment_ids(fail):
    repo, llm, service, chat_id, schedule_id = setup([])
    before = copy.deepcopy(repo.profiles[TEAM])
    original = repo.assignments(schedule_id, TEAM)[0]
    llm._answers += [structure_proposal(repo), generated([("דנה", "יום"), ("יוסי", "לילה")])]
    message = converse(service, repo, chat_id, schedule_id, "תשנה את המשמרות ל12–00 ו00–12 ביום שלישי")
    assert message["status"] == "pending", message["content"]
    assert repo.profiles[TEAM] == before
    if fail:
        def rejected_write(*args, **kwargs):
            raise RuntimeError("write failed")
        repo.add_assignment = rejected_write
        with pytest.raises(RuntimeError):
            service.apply(TEAM, "manager-a", chat_id, message["id"])
        assert repo.profiles[TEAM] == before and repo.assignments(schedule_id, TEAM) == [original]
    else:
        service.apply(TEAM, "manager-a", chat_id, message["id"])
        assignments = repo.assignments(schedule_id, TEAM)
        assert assignments[0]["id"] == original["id"]
        assert {row["shift"] for row in assignments if row["date"] == "2026-10-06"} == {"יום", "לילה"}
        assert {row["name"] for row in repo.profiles[TEAM]["shifts"]} == {"יום", "לילה"}
        stats = shift_stats(assignments, repo.profiles[TEAM]["shifts"], repo.profiles[TEAM]["employees"],
                            slots=repo.get_schedule(schedule_id, TEAM)["slots"], profile=repo.profiles[TEAM])
        assert stats["total_hours"] >= 24


def test_copy_translates_dates_without_asking_the_scheduler_to_choose_people():
    proposal = turn("generate", copy_from_date="2026-10-05")
    proposal.update(starts_on="2026-10-12", ends_on="2026-10-12")
    repo, llm, service, chat_id, schedule_id = setup([proposal])
    message = converse(service, repo, chat_id, schedule_id, "תשבץ את שני כמו בשבוע שעבר")
    assert message["status"] == "pending", message["content"]
    assert message["payload"]["plan"]["generated"]["assignments"][0]["employee"] == "דנה"
    assert message["payload"]["plan"]["generated"]["assignments"][0]["date"] == "2026-10-12"
    assert len(llm.calls) == 1
