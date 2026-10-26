"""A chat change that leaves a seat empty: the solver picks who fills it."""

from app.bl.chat_vacancies import vacated_slots
from app.bl.manager_chat import ManagerChatService
from app.bl.schedule_service import ScheduleService
from tests.test_manager_chat import ChatRepo, TEAM, MORNING, converse, setup, sickness, translation
from tests.test_schedule_api import _ScriptedLlm


def removal_only(**extra):
    proposal = sickness()
    proposal["operations"] = proposal["operations"][:1]
    proposal.update(extra)
    return proposal


def test_a_removal_with_no_named_replacement_is_filled_by_the_solver():
    repo, _, service, chat_id, schedule_id = setup([removal_only(), translation()])
    message = converse(service, repo, chat_id, schedule_id, "תוריד את דנה מהבוקר של 2026-10-05")
    assert message["status"] == "pending", message["content"]
    operations = message["payload"]["plan"]["operations"]
    assert [(row["action"], row["employee"]) for row in operations] == [("remove", "דנה"), ("assign", "יוסי")]
    assert operations[1]["reason"]
    assert "ה-solver בחר" in message["content"] and "יוסי" in message["content"]
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"
    service.apply(TEAM, "manager-a", chat_id, message["id"], True)
    assert [row["employee"] for row in repo.assignments(schedule_id, TEAM)] == ["יוסי"]


def test_a_named_replacement_does_not_call_the_solver():
    repo, llm, service, chat_id, schedule_id = setup([sickness()])
    message = converse(service, repo, chat_id, schedule_id)
    assert len(message["payload"]["plan"]["operations"]) == 2
    assert "solver_note" not in message["payload"]["plan"]
    assert len(llm.calls) == 1


def test_leave_vacant_keeps_the_seat_empty():
    repo, llm, service, chat_id, schedule_id = setup([removal_only(leave_vacant=True)])
    message = converse(service, repo, chat_id, schedule_id, "תוריד את דנה ותשאיר את המשמרת ריקה")
    assert [row["action"] for row in message["payload"]["plan"]["operations"]] == ["remove"]
    assert len(llm.calls) == 1


def test_only_slots_that_lost_people_are_vacated():
    before = [dict(employee="דנה", shift=MORNING, date="2026-10-05"),
              dict(employee="יוסי", shift=MORNING, date="2026-10-06")]
    after = [dict(employee="יוסי", shift=MORNING, date="2026-10-05")]
    operations = [dict(action="remove", employee="דנה", shift=MORNING, date="2026-10-05"),
                  dict(action="remove", employee="יוסי", shift=MORNING, date="2026-10-06"),
                  dict(action="assign", employee="יוסי", shift=MORNING, date="2026-10-05")]
    assert vacated_slots(before, after, operations) == [(MORNING, "2026-10-06")]


def test_chat_builds_use_the_live_solver_settings():
    repo, llm = ChatRepo(), _ScriptedLlm([])
    store = object()
    service = ManagerChatService(repo, llm, ScheduleService(repo, llm), settings=store)
    assert service._planner._scheduler._settings is store
