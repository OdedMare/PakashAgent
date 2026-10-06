"""Manager scenarios: private history, real previews and all-or-nothing clicks."""

import copy
import json
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.dependencies.dependencies import Guards
from app.api.routers.manager_chat import build_router
from app.bl.manager_chat import ManagerChatService
from app.bl.schedule_service import ScheduleService
from app.common.errors.errors import AppError, ConflictError, NotFoundError, error_payload
from app.common.sessions.sessions import COOKIE_NAME, ROLE_BOSS, ROLE_MEMBER, issue
from tests.test_schedule_api import _FakeScheduleRepo, _ScriptedLlm, PROFILE, TEAM, SECRET, MORNING


class ChatRepo(_FakeScheduleRepo):
    def __init__(self):
        super().__init__()
        self.profiles = {TEAM: copy.deepcopy(PROFILE)}
        self.chats = {}
        self.progress = []

    def create_chat(self, team_id, manager_id):
        chat_id = self._id("chat")
        self.chats[chat_id] = dict(id=chat_id, team_id=team_id, manager_id=manager_id,
                                   title="שיחה חדשה", messages=[])
        return self.get_chat(team_id, manager_id, chat_id)

    def get_chat(self, team_id, manager_id, chat_id):
        chat = self.chats.get(chat_id)
        if not chat or (chat["team_id"], chat["manager_id"]) != (team_id, manager_id):
            raise NotFoundError("השיחה לא נמצאה")
        return copy.deepcopy(chat)

    def list_chats(self, team_id, manager_id):
        return [dict(id=row["id"], title=row["title"]) for row in self.chats.values()
                if (row["team_id"], row["manager_id"]) == (team_id, manager_id)]

    def start_chat_turn(self, team_id, manager_id, chat_id, content, request_id, payload):
        chat = self.get_chat(team_id, manager_id, chat_id)
        if any(row.get("request_id") == request_id for row in chat["messages"]):
            return None
        if any(row["status"] == "working" for row in chat["messages"]):
            raise ConflictError("עדיין עובד")
        for row in self.chats[chat_id]["messages"]:
            if row["status"] == "pending":
                row["status"] = "superseded"
        message_id = self._id("message")
        self.chats[chat_id]["messages"] += [
            dict(id=self._id("user"), role="user", content=content, status="complete", payload={}, request_id=request_id),
            dict(id=message_id, role="assistant", content="", status="working", payload=payload),
        ]
        return message_id

    def finish_chat_turn(self, chat_id, message_id, content, status, payload):
        for row in self.chats[chat_id]["messages"]:
            if row["id"] == message_id and row["status"] == "working":
                row.update(content=content, status=status, payload=payload)

    def chat_turn_progress(self, chat_id, message_id, payload):
        self.progress.append(copy.deepcopy(payload))
        for row in self.chats[chat_id]["messages"]:
            if row["id"] == message_id and row["status"] == "working":
                row["payload"] = payload

    @contextmanager
    def chat_approval(self, team_id, manager_id, chat_id, message_id):
        chat = self.get_chat(team_id, manager_id, chat_id)
        row = next(row for row in chat["messages"] if row["id"] == message_id)
        if row["status"] not in ("pending", "applied"):
            raise ConflictError("הצעה ישנה")
        before = copy.deepcopy(self.__dict__)
        try:
            yield row
        except Exception:
            self.__dict__.update(before)
            raise

    def mark_chat_applied(self, chat_id, message_id, payload):
        row = next(row for row in self.chats[chat_id]["messages"] if row["id"] == message_id)
        row.update(status="applied", payload=payload)

    def record_chat_confirmation(self, chat_id, content, request_id, receipt):
        self.chats[chat_id]["messages"] += [
            dict(id=self._id("user"), role="user", content=content, status="complete", payload={}, request_id=request_id),
            dict(id=self._id("receipt"), role="assistant", content=receipt["message"], status="complete", payload={"receipt": receipt}),
        ]

    def replace_span_slots(self, schedule_id, team_id, first, last, slots):
        self.get_schedule(schedule_id, team_id)
        self.slots[schedule_id] = [row for row in self.slots[schedule_id]
                                  if not first <= row["slot_date"] <= last] + [
            dict(row, id=self._id("slot"), team_id=team_id) for row in slots]


def turn(kind="answer", **kwargs):
    return dict(kind=kind, reply="הנה התוכנית", needs_reason=False, needs_input=False,
                operations=[], constraints=[], profile_operations=[], exceptions=[],
                agent_reason="יוסי מוסמך וזמין, והעומס שלו מתאים", stated_reason="דנה חולה",
                schedule_id="", profile_patch_json="", starts_on="", ends_on="",
                instructions="", replace_existing=False, question=None, tool_calls=[], **kwargs)


def setup(answers):
    repo, llm = ChatRepo(), _ScriptedLlm(answers)
    schedule = repo.create_schedule(TEAM, "2026-10-04", "2026-10-10")
    slots = repo.replace_slots(schedule["id"], TEAM, [{"shift_name": MORNING, "slot_date": "2026-10-05", "headcount": 1}])
    repo.add_assignment(schedule["id"], TEAM, slots[0]["id"], "דנה", "שיבוץ קיים")
    chat = repo.create_chat(TEAM, "manager-a")
    service = ManagerChatService(repo, llm, ScheduleService(repo, llm))
    return repo, llm, service, chat["id"], schedule["id"]


def converse(service, repo, chat_id, schedule_id, content="דנה חולה מחר", request_id="request-1"):
    message_id = service.start_turn(TEAM, "manager-a", chat_id, dict(content=content,
        request_id=request_id, schedule_id=schedule_id, visible_week="2026-10-04"))
    if message_id:
        service.reply(TEAM, "manager-a", chat_id, message_id)
    return repo.get_chat(TEAM, "manager-a", chat_id)["messages"][-1]


def sickness():
    result = turn("changes")
    result["operations"] = [
        dict(action="remove", employee="דנה", shift=MORNING, date="2026-10-05", reason="מחלה"),
        dict(action="assign", employee="יוסי", shift=MORNING, date="2026-10-05", reason="זמין ומוסמך"),
    ]
    result["constraints"] = [dict(employee="דנה", shift="", date="2026-10-05", reason="מחלה", available=False)]
    return result


def test_sickness_preview_writes_nothing_then_click_applies_plan_and_absence_once():
    repo, llm, service, chat_id, schedule_id = setup([sickness()])
    message = converse(service, repo, chat_id, schedule_id)
    assert message["status"] == "pending"
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"
    assert not repo.availability_rows and not repo.changes
    service.apply(TEAM, "manager-a", chat_id, message["id"], True)
    assert [row["employee"] for row in repo.assignments(schedule_id, TEAM)] == ["יוסי"]
    assert repo.availability_rows[0]["available"] is False
    assert repo.availability_rows[0]["reason"] == "מחלה"
    change_count = len(repo.changes)
    service.apply(TEAM, "manager-a", chat_id, message["id"], True)
    assert len(repo.changes) == change_count


def test_saved_setup_and_previous_conversation_reach_model():
    repo, llm, service, chat_id, schedule_id = setup([turn(), turn()])
    repo.profiles[TEAM]["rest_policy"] = "מנוחה לפי כללי היחידה"
    repo.profiles[TEAM]["training_policy"] = {"trainer_required": True}
    converse(service, repo, chat_id, schedule_id, "מי מתאים?", "first")
    converse(service, repo, chat_id, schedule_id, "ומה עם העובד השני?", "second")
    payload = json.loads(llm.calls[-1]["user"])
    assert payload["profile"]["rest_policy"] == "מנוחה לפי כללי היחידה"
    assert payload["profile"]["training_policy"] == {"trainer_required": True}
    assert any(row["content"] == "מי מתאים?" for row in payload["conversation"])


def test_stale_recommendation_cannot_overwrite_a_new_manual_change():
    repo, _, service, chat_id, schedule_id = setup([sickness()])
    message = converse(service, repo, chat_id, schedule_id)
    repo.set_availability(TEAM, "יוסי", "2026-10-05", reason="חופשה")
    with pytest.raises(ConflictError, match="השתנו"):
        service.apply(TEAM, "manager-a", chat_id, message["id"], True)
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"


def test_rule_exception_requires_explicit_click_and_does_not_change_saved_rule():
    proposal = sickness()
    proposal["exceptions"] = ["חריגה מכלל צוות שהמנהל קבע"]
    repo, _, service, chat_id, schedule_id = setup([proposal])
    original = copy.deepcopy(repo.profiles[TEAM])
    message = converse(service, repo, chat_id, schedule_id)
    with pytest.raises(ConflictError, match="במפורש"):
        service.apply(TEAM, "manager-a", chat_id, message["id"])
    service.apply(TEAM, "manager-a", chat_id, message["id"], True)
    assert repo.profiles[TEAM] == original
    assert "חריגה מכלל צוות" in repo.changes[-1]["agent_reason"]


def test_second_write_failure_rolls_back_the_entire_plan():
    repo, _, service, chat_id, schedule_id = setup([sickness()])
    message = converse(service, repo, chat_id, schedule_id)
    def fail(*args, **kwargs):
        raise RuntimeError("simulated assignment write failure")
    repo.add_assignment = fail
    with pytest.raises(RuntimeError):
        service.apply(TEAM, "manager-a", chat_id, message["id"], True)
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"
    assert not repo.availability_rows and not repo.changes
    assert repo.get_chat(TEAM, "manager-a", chat_id)["messages"][-1]["status"] == "pending"


def test_add_employee_preview_preserves_existing_fields_and_applies_profile():
    proposal = turn("profile")
    repo, _, service, chat_id, schedule_id = setup([])
    profile = repo.profiles[TEAM]
    profile["employees"][0].update(rotation_group="א", can_train=True, notes="חשוב")
    proposal["profile_patch_json"] = json.dumps({"employees": profile["employees"] + [
        {"name": "מאיה", "role": "נציגת שירות", "eligible_shifts": [MORNING],
         "rotation_group": "ב", "exit_pattern": "round", "service_type": "standard"},
    ]})
    service._llm._answers.append(proposal)
    message = converse(service, repo, chat_id, schedule_id, "תוסיף את מאיה לצוות")
    assert message["status"] == "pending" and len(profile["employees"]) == 2
    service.apply(TEAM, "manager-a", chat_id, message["id"])
    updated = repo.profiles[TEAM]
    assert len(updated["employees"]) == 3
    assert updated["employees"][0]["can_train"] is True
    assert updated["employees"][0]["notes"] == "חשוב"


def test_workload_is_computed_by_tool_and_tool_results_feed_final_answer():
    calls = turn()
    calls["tool_calls"] = [dict(tool="workload_report", arguments={})]
    repo, llm, service, chat_id, schedule_id = setup([calls, turn()])
    message = converse(service, repo, chat_id, schedule_id, "מי עובד הכי הרבה?")
    stats = message["payload"]["results"][0]["stats"]
    assert stats["by_employee"][0]["employee"] == "דנה"
    assert stats["by_employee"][0]["hours"] == 8
    assert json.loads(llm.calls[-1]["user"])["results"][0]["basis"] == "scheduled"


def test_tool_on_empty_visible_week_cannot_report_todays_schedule():
    calls = turn()
    calls["tool_calls"] = [dict(tool="read_period", arguments={})]
    repo, llm, service, chat_id, _ = setup([calls, turn()])
    message_id = service.start_turn(TEAM, "manager-a", chat_id, {
        "content": "מי עובד כאן?", "request_id": "blank-week", "schedule_id": "",
        "visible_week": "2026-10-18",
    })
    service.reply(TEAM, "manager-a", chat_id, message_id)
    assert json.loads(llm.calls[-1]["user"])["results"][0]["found"] is False


def test_generate_upcoming_week_previews_real_assignments_without_touching_current_week():
    proposal = turn("generate")
    proposal.update(starts_on="2026-10-11", ends_on="2026-10-17")
    generation = {"assignments": [dict(employee="דנה", shift=MORNING, date="2026-10-11", reason="מתאימה")],
                  "notes": [], "summary": "סידור מוצע"}
    repo, _, service, chat_id, schedule_id = setup([proposal, generation, generation])
    message = converse(service, repo, chat_id, schedule_id, "תשבץ את השבוע הבא")
    assert message["status"] == "pending"
    assert len(repo.schedules) == 1
    assert message["payload"]["plan"]["generated"]["assignments"][0]["date"] == "2026-10-11"
    service.apply(TEAM, "manager-a", chat_id, message["id"], True)
    assert len(repo.schedules) == 2
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"


def test_day_opened_from_board_rebuilds_only_that_day_and_keeps_the_rest():
    proposal = turn("generate", required_assignments=[])
    proposal.update(starts_on="2026-10-06", ends_on="2026-10-06", replace_existing=True,
                    instructions="לתת עדיפות ליוסי")
    span = {"assignments": [dict(employee="יוסי", shift=MORNING, date="2026-10-06", reason="לפי ההנחיה")],
            "notes": [], "summary": "יום שלישי שובץ"}
    repo, llm, service, chat_id, schedule_id = setup([proposal, span])
    repo.assignment_rows[schedule_id] = []
    repo.replace_slots(schedule_id, TEAM, [
        {"shift_name": MORNING, "slot_date": "2026-10-05", "headcount": 1},
        {"shift_name": MORNING, "slot_date": "2026-10-06", "headcount": 1},
    ])
    slots = {row["slot_date"]: row["id"] for row in repo.get_schedule(schedule_id, TEAM)["slots"]}
    repo.add_assignment(schedule_id, TEAM, slots["2026-10-05"], "דנה", "שיבוץ קיים")
    message_id = service.start_turn(TEAM, "manager-a", chat_id, dict(
        content="תשבץ את היום", request_id="day-1", schedule_id=schedule_id,
        visible_week="2026-10-04", focus_date="2026-10-06"))
    service.reply(TEAM, "manager-a", chat_id, message_id)
    message = repo.get_chat(TEAM, "manager-a", chat_id)["messages"][-1]
    assert json.loads(llm.calls[0]["user"])["focused_date"] == "2026-10-06"
    assert message["status"] == "pending", message["content"]
    plan = message["payload"]["plan"]
    assert (plan["starts_on"], plan["ends_on"]) == ("2026-10-06", "2026-10-06")
    service.apply(TEAM, "manager-a", chat_id, message["id"], True)
    rows = sorted((row["employee"], str(row["date"])[:10]) for row in repo.assignments(schedule_id, TEAM))
    assert rows == [("דנה", "2026-10-05"), ("יוסי", "2026-10-06")]
    assert len(repo.schedules) == 1


def test_malformed_focus_date_is_dropped_rather_than_shown_to_the_model():
    repo, llm, service, chat_id, schedule_id = setup([turn()])
    message_id = service.start_turn(TEAM, "manager-a", chat_id, dict(
        content="מה חסר?", request_id="day-2", schedule_id=schedule_id, focus_date="not-a-day"))
    service.reply(TEAM, "manager-a", chat_id, message_id)
    assert json.loads(llm.calls[0]["user"])["focused_date"] == ""


def unknown_slot():
    proposal = sickness()
    proposal["operations"][1]["shift"] = "משמרת שלא קיימת"
    return proposal


def test_unknown_slot_does_not_silently_apply_only_half_the_plan():
    # Refused, handed back twice, and still wrong: the turn fails with no plan.
    repo, llm, service, chat_id, schedule_id = setup([unknown_slot(), unknown_slot(), unknown_slot()])
    message = converse(service, repo, chat_id, schedule_id)
    assert message["status"] == "error" and "plan" not in message["payload"]
    assert len(llm.calls) == 3
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"


def test_refused_plan_is_handed_back_and_the_corrected_plan_is_offered():
    repo, llm, service, chat_id, schedule_id = setup([unknown_slot(), sickness()])
    message = converse(service, repo, chat_id, schedule_id)
    assert message["status"] == "pending", message["content"]
    check = json.loads(llm.calls[1]["user"])["results"][-1]
    assert check["tool"] == "plan_check" and check["ok"] is False and check["error"]
    assert [step["tool"] for step in message["payload"]["steps"]] == ["plan_check"]
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"


def test_clear_instruction_is_previewed_and_logged_without_a_separate_reason():
    proposal = sickness()
    proposal["stated_reason"] = ""
    proposal["constraints"] = []
    repo, llm, service, chat_id, schedule_id = setup([proposal])
    request = "תחליף את דנה ביוסי"
    message = converse(service, repo, chat_id, schedule_id, request)
    assert len(llm.calls) == 1
    assert message["status"] == "pending" and message["payload"]["plan"]["reason"] == request
    service.apply(TEAM, "manager-a", chat_id, message["id"])
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "יוסי"
    assert repo.changes[-1]["reason"] == request


def test_model_reason_question_is_repaired_without_asking_manager_again():
    asked = turn()
    asked.update(needs_reason=True, reply="מה הסיבה לשינוי?", stated_reason="")
    fixed = sickness()
    fixed.update(stated_reason="", constraints=[])
    repo, llm, service, chat_id, schedule_id = setup([asked, fixed])
    message = converse(service, repo, chat_id, schedule_id, "תחליף את דנה ביוסי")
    assert message["status"] == "pending"
    assert json.loads(llm.calls[1]["user"])["results"][-1]["tool"] == "plan_check"


def test_empty_final_answer_is_repaired_instead_of_sending_a_generic_question():
    empty = turn()
    empty["reply"] = " "
    answer = turn()
    answer["reply"] = "כדאי להתחיל בבדיקת הזמינות ולחלק את העומס בין העובדים הזמינים."
    repo, llm, service, chat_id, _ = setup([empty, answer])
    request = "איך כדאי לפתור עומס בצוות?"
    message = converse(service, repo, chat_id, "", request)
    assert message["status"] == "complete" and message["content"] == answer["reply"]
    payload = json.loads(llm.calls[1]["user"])
    assert payload["current_request"] == request
    assert payload["results"][-1]["tool"] == "plan_check"
    assert not repo.changes


def test_answer_with_mutations_is_repaired_instead_of_silently_dropping_request():
    malformed = sickness()
    malformed["kind"] = "answer"
    repo, llm, service, chat_id, schedule_id = setup([malformed, sickness()])
    message = converse(service, repo, chat_id, schedule_id, "תחליף את דנה ביוסי")
    assert message["status"] == "pending" and message["payload"]["plan"]["kind"] == "changes"
    assert json.loads(llm.calls[1]["user"])["results"][-1]["tool"] == "plan_check"
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"


def test_clear_and_constraint_only_requests_do_not_need_justification():
    proposal = turn("clear")
    proposal["stated_reason"] = ""
    repo, _, service, chat_id, schedule_id = setup([proposal])
    message = converse(service, repo, chat_id, schedule_id, "תפנה את כל השיבוצים בשבוע הזה")
    assert message["status"] == "pending"
    service.apply(TEAM, "manager-a", chat_id, message["id"])
    assert not repo.assignments(schedule_id, TEAM)

    constraint = turn("changes")
    constraint.update(stated_reason="", constraints=[dict(
        employee="דנה", date="2026-10-20", shift="", available=False, reason="")])
    repo, _, service, chat_id, schedule_id = setup([constraint])
    repo.schedules[schedule_id]["status"] = "published"
    request = "דנה לא זמינה ב-20 באוקטובר"
    message = converse(service, repo, chat_id, schedule_id, request)
    assert message["status"] == "pending"
    service.apply(TEAM, "manager-a", chat_id, message["id"])
    assert repo.availability_rows[0]["reason"] == request
    assert repo.schedules[schedule_id]["status"] == "published"


def test_consultation_can_simulate_combined_replacement_without_a_plan_or_writes():
    tools = turn()
    tools["tool_calls"] = [dict(tool="simulate_changes", arguments={
        "operations": sickness()["operations"],
    })]
    answer = turn()
    answer["reply"] = "ההחלפה שומרת על הכיסוי; יוסי יקבל 8 שעות ודנה תתפנה."
    repo, llm, service, chat_id, schedule_id = setup([tools, answer])
    message = converse(service, repo, chat_id, schedule_id, "מה יקרה אם נחליף את דנה ביוסי?")
    result = json.loads(llm.calls[1]["user"])["results"][-1]
    assert result["simulated"] and result["coverage"]["delta"] == 0
    assert result["affected"] == ["דנה", "יוסי"]
    assert not result["introduced"]
    assert message["status"] == "complete" and "plan" not in message["payload"]
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"
    assert not repo.changes and not repo.availability_rows


def test_simulation_of_missing_visible_week_cannot_fall_back_to_current_week():
    tools = turn()
    tools["tool_calls"] = [dict(tool="simulate_changes", arguments={
        "operations": sickness()["operations"],
    })]
    repo, llm, service, chat_id, _ = setup([tools, turn()])
    message_id = service.start_turn(TEAM, "manager-a", chat_id, dict(
        content="מה יקרה אם נחליף?", request_id="empty-simulation", schedule_id="",
        visible_week="2026-10-18"))
    service.reply(TEAM, "manager-a", chat_id, message_id)
    result = json.loads(llm.calls[1]["user"])["results"][-1]
    assert result["ok"] is False and "simulated" not in result


def test_simulation_checks_named_week_and_reports_qualification_conflicts():
    repo, _, service, _, focused_id = setup([])
    other = repo.create_schedule(TEAM, "2026-10-11", "2026-10-17")
    repo.replace_slots(other["id"], TEAM, [dict(shift_name=MORNING, slot_date="2026-10-12", headcount=1)])
    repo.profiles[TEAM]["employees"][1]["eligible_shifts"] = ["צהריים"]
    result = service._run_tool(TEAM, "simulate_changes", dict(day="2026-10-12", operations=[
        dict(action="assign", employee="יוסי", shift=MORNING, date="2026-10-12", reason="בדיקה"),
    ]), focused_id)
    assert result["schedule_id"] == other["id"]
    assert any(row["code"] == "ineligible" for row in result["introduced"])
    assert not repo.assignments(other["id"], TEAM)


def test_recurring_constraint_profile_plan_preserves_roster_and_employee_details():
    repo, _, service, chat_id, schedule_id = setup([])
    profile = repo.profiles[TEAM]
    profile["employees"][0].update(can_train=True, rotation_group="א", notes="פרט קיים")
    employees = copy.deepcopy(profile["employees"])
    employees[0]["recurring_constraints"] = [dict(days=["שלישי"], shifts=[], available=False,
                                                reason="אילוץ קבוע")]
    proposal = turn("profile")
    proposal.update(stated_reason="", profile_patch_json=json.dumps(dict(employees=employees)))
    service._llm._answers.append(proposal)
    message = converse(service, repo, chat_id, schedule_id, "דנה לא זמינה בכל יום שלישי")
    assert message["status"] == "pending"
    assert "recurring_constraints" not in profile["employees"][0]
    service.apply(TEAM, "manager-a", chat_id, message["id"])
    updated = repo.profiles[TEAM]["employees"]
    assert updated[0]["recurring_constraints"] == employees[0]["recurring_constraints"]
    assert updated[0]["can_train"] and updated[0]["rotation_group"] == "א"
    assert updated[0]["notes"] == "פרט קיים" and len(updated) == 2
    assert not repo.availability_rows
    from app.bl.scheduler.availability import effective_availability
    recurring = [row for row in effective_availability(repo.profiles[TEAM], [], "2026-10-04", "2026-10-10")
                 if row["source"] == "interview"]
    assert [(row["date"], row["shift"]) for row in recurring] == [("2026-10-06", MORNING)]


def test_malformed_recurring_scope_is_repaired_instead_of_blocking_entire_week():
    repo, llm, service, chat_id, schedule_id = setup([])
    employees = copy.deepcopy(repo.profiles[TEAM]["employees"])
    employees[0]["recurring_constraints"] = [dict(day_of_week=2, shift=MORNING, available=False)]
    malformed = turn("profile")
    malformed["profile_patch_json"] = json.dumps(dict(employees=employees))
    employees[0]["recurring_constraints"] = [dict(days=["שלישי"], shifts=[MORNING], available=False)]
    fixed = turn("profile")
    fixed["profile_patch_json"] = json.dumps(dict(employees=employees))
    llm._answers.extend([malformed, fixed])
    message = converse(service, repo, chat_id, schedule_id, "דנה לא זמינה בכל שלישי בבוקר")
    assert message["status"] == "pending"
    assert "days" in json.loads(llm.calls[1]["user"])["results"][-1]["error"]
    assert message["payload"]["plan"]["profile_after"]["employees"][0]["recurring_constraints"] == \
        employees[0]["recurring_constraints"]


def test_partial_employee_row_cannot_erase_existing_qualifications_or_notes():
    proposal = turn("profile")
    proposal["profile_patch_json"] = json.dumps(dict(employees=[
        dict(name="דנה", recurring_constraints=[dict(days=["שלישי"], shifts=[], available=False)]),
        dict(name="יוסי"),
    ]))
    repo, _, service, chat_id, schedule_id = setup([proposal])
    repo.profiles[TEAM]["employees"][0].update(can_train=True, notes="חשוב", rotation_group="א")
    message = converse(service, repo, chat_id, schedule_id, "הוסף אילוץ לשלישי")
    assert message["status"] == "pending"
    employee = message["payload"]["plan"]["profile_after"]["employees"][0]
    assert employee["eligible_shifts"] == [MORNING] and employee["can_train"]
    assert employee["notes"] == "חשוב" and employee["rotation_group"] == "א"


def test_combined_conflicts_reach_agent_and_corrected_plan_keeps_absence():
    proposal = sickness()
    repo, llm, service, chat_id, schedule_id = setup([proposal])
    repo.set_availability(TEAM, "יוסי", "2026-10-05", reason="חופשה")
    repo.profiles[TEAM]["employees"].append(dict(name="מאיה", eligible_shifts=[MORNING]))
    fixed = sickness()
    fixed["operations"][1]["employee"] = "מאיה"
    llm._answers.append(fixed)
    message = converse(service, repo, chat_id, schedule_id)
    review = json.loads(llm.calls[1]["user"])["results"][-1]
    assert review["tool"] == "plan_review"
    assert any(row["code"] == "unavailable" for row in review["plan"]["warnings"])
    plan = message["payload"]["plan"]
    assert plan["operations"][1]["employee"] == "מאיה" and not plan["warnings"]
    assert plan["constraints"] == fixed["constraints"]


def test_known_qualification_conflict_is_visible_and_requires_exception_approval():
    proposal = sickness()
    proposal["exceptions"] = ["יוסי אינו מוסמך לבוקר לפי הפרופיל"]
    repo, _, service, chat_id, schedule_id = setup([proposal])
    repo.profiles[TEAM]["employees"][1]["eligible_shifts"] = ["צהריים"]
    message = converse(service, repo, chat_id, schedule_id)
    assert any(row["code"] == "ineligible" for row in message["payload"]["plan"]["warnings"])
    with pytest.raises(ConflictError):
        service.apply(TEAM, "manager-a", chat_id, message["id"])


def test_unrelated_existing_gaps_do_not_hold_a_valid_replacement():
    repo, llm, service, chat_id, schedule_id = setup([sickness()])
    repo.slots[schedule_id].append(dict(id="empty-slot", shift_name=MORNING,
                                      slot_date="2026-10-06", headcount=1))
    message = converse(service, repo, chat_id, schedule_id)
    assert message["status"] == "pending" and len(llm.calls) == 1
    assert not message["payload"]["plan"]["warnings"]


def test_duplicate_assignment_is_repaired_before_it_can_reach_storage():
    duplicate = sickness()
    duplicate["operations"].append(copy.deepcopy(duplicate["operations"][-1]))
    repo, llm, service, chat_id, schedule_id = setup([duplicate, sickness()])
    message = converse(service, repo, chat_id, schedule_id)
    assert message["status"] == "pending"
    assert "פעמיים" in json.loads(llm.calls[1]["user"])["results"][-1]["error"]
    service.apply(TEAM, "manager-a", chat_id, message["id"])
    assert len(repo.assignments(schedule_id, TEAM)) == 1


def test_last_round_answers_from_what_was_checked_instead_of_failing():
    calls = turn()
    calls["tool_calls"] = [dict(tool="list_periods", arguments={})]
    final = turn()
    final.update(reply="לפי מה שנבדק", tool_calls=[dict(tool="list_periods", arguments={})])
    repo, llm, service, chat_id, schedule_id = setup([calls] * 6 + [final])
    message = converse(service, repo, chat_id, schedule_id, "מה יש?")
    assert message["status"] == "complete" and message["content"] == "לפי מה שנבדק"
    assert json.loads(llm.calls[-1]["user"])["final_round"] is True
    assert len(message["payload"]["steps"]) == 6


def test_extra_tool_calls_are_refused_out_loud_and_progress_is_saved_each_round():
    calls = turn()
    calls["tool_calls"] = [dict(tool="list_periods", arguments={})] * 5
    repo, llm, service, chat_id, schedule_id = setup([calls, turn()])
    converse(service, repo, chat_id, schedule_id, "מה יש?")
    results = json.loads(llm.calls[-1]["user"])["results"]
    assert len(results) == 5 and results[0]["ok"] is False and "נדחה" in results[0]["error"]
    assert len(repo.progress[0]["steps"]) == 4
    assert repo.progress[0]["schedule_id"] == schedule_id


def test_failed_tool_is_reported_to_the_model_rather_than_ending_the_turn():
    calls = turn()
    calls["tool_calls"] = [dict(tool="workload_report", arguments={"starts_on": "2026-10-10"})]
    repo, llm, service, chat_id, schedule_id = setup([calls, turn()])
    message = converse(service, repo, chat_id, schedule_id, "כמה עבדו?")
    assert message["status"] == "complete"
    assert json.loads(llm.calls[-1]["user"])["results"][0]["ok"] is False


def test_only_the_newest_plan_and_recent_checks_are_resent_in_full():
    tools = turn()
    tools["tool_calls"] = [dict(tool="list_periods", arguments={})]
    repo, llm, service, chat_id, schedule_id = setup(
        [tools, turn(), tools, turn(), tools, turn(), sickness(), sickness(), turn()])
    for index in range(6):
        converse(service, repo, chat_id, schedule_id, "שאלה %d" % index, "r%d" % index)
    conversation = json.loads(llm.calls[-1]["user"])["conversation"]
    plans = [row["context"]["plan"] for row in conversation if "plan" in row["context"]]
    assert plans[0]["summarized"] is True and plans[0]["operations"] == 2
    assert "operations" in plans[1] and isinstance(plans[1]["operations"], list)
    assert all("snapshot" not in plan for plan in plans)
    full = [row for row in conversation if "results" in row["context"]]
    trimmed = [row for row in conversation if "checked" in row["context"]]
    assert len(full) == 2 and trimmed[0]["context"]["checked"] == ["list_periods"]


def test_adjusting_generated_preview_preserves_other_choices_and_remains_read_only():
    proposal = turn("generate")
    proposal.update(starts_on="2026-10-11", ends_on="2026-10-17",
                    required_assignments=[
                        dict(employee="יוסי", shift=MORNING, date="2026-10-11"),
                        dict(employee="דנה", shift=MORNING, date="2026-10-12"),
                    ])
    repo, llm, service, chat_id, schedule_id = setup([proposal, {
        "assignments": [], "notes": [], "summary": "הבחירות נשמרו",
    }, {
        "assignments": [], "notes": [], "summary": "הבחירות נשמרו, נותרו חוסרים",
    }])
    message = converse(service, repo, chat_id, schedule_id, "במקום דנה ביום ראשון תציע את יוסי")
    assert message["status"] == "pending"
    assignments = message["payload"]["plan"]["generated"]["assignments"]
    assert [(row["employee"], row["date"]) for row in assignments] == [
        ("יוסי", "2026-10-11"), ("דנה", "2026-10-12"),
    ]
    assert len(json.loads(llm.calls[-1]["user"])["required_assignments"]) == 2
    assert len(repo.schedules) == 1


def test_future_absence_can_be_approved_before_a_schedule_exists():
    proposal = turn("changes")
    proposal["constraints"] = [dict(employee="דנה", date="2026-10-20", shift="",
                                    available=False, reason="מחלה")]
    repo, _, service, chat_id, _ = setup([proposal])
    message = converse(service, repo, chat_id, "", "דנה לא תהיה זמינה ב-20 באוקטובר")
    assert message["status"] == "pending" and not repo.availability_rows
    service.apply(TEAM, "manager-a", chat_id, message["id"])
    assert repo.availability_rows[0]["constraint_date"] == "2026-10-20"
    assert repo.availability_rows[0]["available"] is False


def test_two_managers_cannot_read_or_apply_each_others_private_conversation():
    repo, _, service, _, _ = setup([])
    app = FastAPI()
    app.include_router(build_router(service, repo, Guards(SECRET)))
    @app.exception_handler(AppError)
    async def error(request, exc):
        return JSONResponse(status_code=exc.status_code, content=error_payload(exc))
    first, second = TestClient(app), TestClient(app)
    for client in (first, second):
        client.cookies.set(COOKIE_NAME, issue(SECRET, TEAM, ROLE_BOSS, 30))
    chat = first.post("/api/agent/chats").json()
    assert second.get("/api/agent/chats/" + chat["id"]).status_code == 404
    assert second.post("/api/agent/chats/%s/messages/missing/apply" % chat["id"], json={}).status_code == 404
    member = TestClient(app)
    member.cookies.set(COOKIE_NAME, issue(SECRET, TEAM, ROLE_MEMBER, 30))
    assert member.get("/api/agent/chats").status_code == 401


def test_retry_request_id_does_not_duplicate_messages():
    repo, llm, service, chat_id, schedule_id = setup([turn()])
    converse(service, repo, chat_id, schedule_id)
    converse(service, repo, chat_id, schedule_id)
    assert len(repo.get_chat(TEAM, "manager-a", chat_id)["messages"]) == 2
    assert len(llm.calls) == 1
