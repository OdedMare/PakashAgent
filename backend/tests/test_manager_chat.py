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
        {"name": "מאיה", "role": "נציגת שירות", "eligible_shifts": [MORNING], "rotation_group": "ב"},
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


def test_generate_upcoming_week_previews_real_assignments_without_touching_current_week():
    proposal = turn("generate")
    proposal.update(starts_on="2026-10-11", ends_on="2026-10-17")
    generation = {"assignments": [dict(employee="דנה", shift=MORNING, date="2026-10-11", reason="מתאימה")],
                  "notes": [], "summary": "סידור מוצע"}
    repo, _, service, chat_id, schedule_id = setup([proposal, generation])
    message = converse(service, repo, chat_id, schedule_id, "תשבץ את השבוע הבא")
    assert message["status"] == "pending"
    assert len(repo.schedules) == 1
    assert message["payload"]["plan"]["generated"]["assignments"][0]["date"] == "2026-10-11"
    service.apply(TEAM, "manager-a", chat_id, message["id"], True)
    assert len(repo.schedules) == 2
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"


def test_unknown_slot_does_not_silently_apply_only_half_the_plan():
    proposal = sickness()
    proposal["operations"][1]["shift"] = "משמרת שלא קיימת"
    repo, _, service, chat_id, schedule_id = setup([proposal])
    message = converse(service, repo, chat_id, schedule_id)
    assert message["status"] == "error" and "plan" not in message["payload"]
    assert repo.assignments(schedule_id, TEAM)[0]["employee"] == "דנה"


def test_adjusting_generated_preview_preserves_other_choices_and_remains_read_only():
    proposal = turn("generate")
    proposal.update(starts_on="2026-10-11", ends_on="2026-10-17",
                    required_assignments=[
                        dict(employee="יוסי", shift=MORNING, date="2026-10-11"),
                        dict(employee="דנה", shift=MORNING, date="2026-10-12"),
                    ])
    repo, llm, service, chat_id, schedule_id = setup([proposal, {
        "assignments": [], "notes": [], "summary": "הבחירות נשמרו",
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
