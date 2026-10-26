"""An absence read and planned in code: dates, follow-ups and fair covers."""

import pytest

from app.bl.absence.dates import dates_in
from app.bl.absence.reader import read
from tests.test_manager_chat import TEAM, MORNING, converse, setup

TODAY, WEEK = "2026-10-23", "2026-10-25"
ROSTER = ["עודד", "ירין עמלקית", "יוסי", "דנה"]


@pytest.mark.parametrize("sentence, expected", [
    ("עודד חולה בשני ושלישי", ["2026-10-26", "2026-10-27"]),
    ("עודד בחופש מראשון עד רביעי", ["2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28"]),
    ("עודד במילואים מ-1.11 עד ה-5.11", ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]),
    ("עודד חולה היום ומחר", ["2026-10-23", "2026-10-24"]),
    ("עודד חולה כל השבוע", ["2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28",
                            "2026-10-29", "2026-10-30", "2026-10-31"]),
    ("עודד חולה ב-2026-10-27", ["2026-10-27"]),
    ("עודד חולה כבר שבוע", []),
    ("עודד טס לחו\"ל", []),
    ("עודד חולה עד 26.10", ["2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26"]),
    ("עודד חולה ממחר עד ה-26.10", ["2026-10-24", "2026-10-25", "2026-10-26"]),
    ("עודד חולה עד יום שני", ["2026-10-23", "2026-10-24", "2026-10-25", "2026-10-26"]),
])
def test_every_date_a_sentence_names_is_read(sentence, expected):
    assert dates_in(sentence, TODAY, WEEK) == expected


def test_an_absence_until_the_end_of_the_year_is_every_day_from_today():
    days = dates_in("רותי חולה עד 31.12", "2026-10-26")
    assert (days[0], days[-1], len(days)) == ("2026-10-26", "2026-12-31", 67)
    assert dates_in("רותי חולה מ-26.10 עד 31.12", "2026-10-26") == days


@pytest.mark.parametrize("sentence, scope", [
    ("עודד חולה בשני ושלישי תחליף אותו מהלוח", "dates"),
    ("עודד טס לחול אל תשבץ", "ask_dates"),
    ("ירין עמלקית היא לא יכולה לעבוד בשישי", "ask_scope"),
    ("ירין עמלקית לא יכולה לעבוד בכל יום שישי", "recurring"),
    ("עודד לא זמין ב-27.10", "dates"),
])
def test_the_three_shapes_a_manager_types_are_told_apart(sentence, scope):
    found = read(sentence, ROSTER, ["בוקר"], TODAY, WEEK)
    assert found["scope"] == scope


@pytest.mark.parametrize("sentence", [
    "מה יקרה אם עודד חולה בשני",
    "ירין עמלקית לא יכולה לעבוד עם דנה",
    "אל תשבץ את עודד בבוקר",
    "מי יכול להחליף את עודד",
    "עודד ודנה חולים בשני",
    "עודד חולה בשני, יוסי יחליף אותו",
])
def test_anything_not_plainly_one_persons_absence_is_left_to_the_model(sentence):
    assert read(sentence, ROSTER, ["בוקר"], TODAY, WEEK) is None


def test_a_missing_date_is_asked_once_and_the_answer_continues_the_sentence():
    repo, llm, service, chat_id, schedule_id = setup([])
    asked = converse(service, repo, chat_id, schedule_id, "דנה טסה לחו\"ל, אל תשבץ אותה")
    assert asked["status"] == "complete" and "באילו תאריכים" in asked["content"]
    assert asked["payload"]["task"]["kind"] == "absence_dates"
    message = converse(service, repo, chat_id, schedule_id, "מ-5.10 עד 6.10", "dates")
    assert message["status"] == "pending"
    assert [row["date"] for row in message["payload"]["plan"]["constraints"]] == ["2026-10-05", "2026-10-06"]
    assert message["payload"]["plan"]["operations"][0] == dict(
        action="remove", employee="דנה", shift=MORNING, date="2026-10-05",
        reason="דנה טסה לחו\"ל, אל תשבץ אותה מ-5.10 עד 6.10")
    assert not llm.calls and not repo.changes


def test_a_bare_weekday_asks_this_week_or_every_week_and_either_button_plans():
    repo, llm, service, chat_id, schedule_id = setup([])
    asked = converse(service, repo, chat_id, schedule_id, "דנה לא יכולה לעבוד בשני")
    options = asked["payload"]["question"]["options"]
    assert [option["label"] for option in options] == ["רק ביום שני 5.10", "בכל יום שני (אילוץ קבוע)"]
    once = converse(service, repo, chat_id, schedule_id, options[0]["answer"], "once")
    assert once["payload"]["plan"]["kind"] == "changes"
    assert once["payload"]["plan"]["operations"][1]["employee"] == "יוסי"
    always = converse(service, repo, chat_id, schedule_id, options[1]["answer"], "always")
    assert always["payload"]["plan"]["kind"] == "profile"
    rules = always["payload"]["plan"]["profile_after"]["employees"][0]["recurring_constraints"]
    assert [rule["days"] for rule in rules] == [["שני"]]
    assert not llm.calls


def test_covers_are_spread_so_one_person_does_not_take_the_whole_absence():
    repo, llm, service, chat_id, schedule_id = setup([])
    repo.profiles[TEAM]["employees"].append({"name": "רון", "eligible_shifts": [MORNING]})
    tuesday = dict(id=repo._id("slot"), team_id=TEAM, shift_name=MORNING,
                   slot_date="2026-10-06", headcount=1)
    repo.slots[schedule_id].append(tuesday)
    repo.add_assignment(schedule_id, TEAM, tuesday["id"], "דנה", "שיבוץ קיים")
    message = converse(service, repo, chat_id, schedule_id, "דנה חולה בשני ושלישי")
    covers = [row["employee"] for row in message["payload"]["plan"]["operations"]
              if row["action"] == "assign"]
    assert sorted(covers) == ["יוסי", "רון"]
    assert not message["payload"]["plan"]["warnings"]
    assert not llm.calls


def test_an_absence_across_periods_plans_the_first_and_saves_every_date(monkeypatch):
    import datetime
    monkeypatch.setattr("app.bl.absence.fast_path.israel_today", lambda: datetime.date(2026, 10, 4))
    repo, llm, service, chat_id, schedule_id = setup([])
    later = repo.create_schedule(TEAM, "2026-10-11", "2026-10-17")
    slots = repo.replace_slots(later["id"], TEAM, [
        {"shift_name": MORNING, "slot_date": "2026-10-12", "headcount": 1}])
    repo.add_assignment(later["id"], TEAM, slots[0]["id"], "דנה", "שיבוץ קיים")
    message = converse(service, repo, chat_id, schedule_id, "דנה חולה עד 12.10")
    plan = message["payload"]["plan"]
    assert [row["date"] for row in plan["constraints"]][::8] == ["2026-10-04", "2026-10-12"]
    assert [(row["action"], row["date"]) for row in plan["operations"]] == [
        ("remove", "2026-10-05"), ("assign", "2026-10-05")]
    assert "בתקופות מאוחרות" in message["content"]
    assert not llm.calls and not repo.changes


def test_a_hypothetical_is_never_turned_into_a_plan():
    from tests.test_manager_chat import turn
    repo, llm, service, chat_id, schedule_id = setup([turn()])
    message = converse(service, repo, chat_id, schedule_id, "מה יקרה אם דנה תהיה בחופשה ביום שני?")
    assert "plan" not in message["payload"] and "fast_path" not in message["payload"]


def _replacement_client(role):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from app.api.dependencies import Guards
    from app.api.routers.replacements import build_router
    from app.common.errors import AppError, error_payload
    from app.common.sessions import COOKIE_NAME, issue
    from tests.test_manager_chat import SECRET

    repo, llm, service, chat_id, schedule_id = setup([])
    repo.profiles[TEAM]["employees"].append({"name": "רון", "eligible_shifts": [MORNING]})
    app = FastAPI()
    app.include_router(build_router(service, Guards(SECRET)))

    @app.exception_handler(AppError)
    async def error(request, exc):
        return JSONResponse(status_code=exc.status_code, content=error_payload(exc))

    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, issue(SECRET, TEAM, role, 30))
    return repo, llm, client


def test_the_replacement_tab_ranks_covers_for_a_range_and_writes_nothing():
    from app.common.sessions import ROLE_BOSS

    repo, llm, client = _replacement_client(ROLE_BOSS)
    found = client.get("/api/agent/replacements", params=dict(
        employee="דנה", starts_on="2026-10-05", ends_on="2026-10-06")).json()
    assert found["dates"] == ["2026-10-05", "2026-10-06"]
    assert found["free_dates"] == ["2026-10-06"]
    slot = found["slots"][0]
    assert (slot["date"], slot["shift"], slot["replacing"]) == ("2026-10-05", MORNING, "דנה")
    assert slot["pick"] == "יוסי" and slot["picked_by"] == "fairness"
    assert [row["employee"] for row in slot["candidates"]] == ["יוסי", "רון"]
    assert {"hours", "shifts", "nights", "why"} <= set(slot["candidates"][0])
    assert not llm.calls and not repo.changes and not repo.availability_rows


def test_the_replacement_tab_refuses_strangers_and_members():
    from app.common.sessions import ROLE_BOSS, ROLE_MEMBER

    _, _, client = _replacement_client(ROLE_BOSS)
    unknown = client.get("/api/agent/replacements", params=dict(employee="אף אחד", starts_on="2026-10-05"))
    assert unknown.status_code == 400
    _, _, member = _replacement_client(ROLE_MEMBER)
    assert member.get("/api/agent/replacements", params=dict(
        employee="דנה", starts_on="2026-10-05")).status_code == 401


def test_a_code_answered_turn_is_finished_by_the_request_itself():
    repo, llm, service, chat_id, schedule_id = setup([])
    service.start_turn(TEAM, "manager-a", chat_id, dict(
        content="דנה חולה ביום שני", request_id="inline",
        schedule_id=schedule_id, visible_week="2026-10-04"))
    message = repo.get_chat(TEAM, "manager-a", chat_id)["messages"][-1]
    assert message["status"] == "pending" and message["payload"]["fast_path"] == "absence"
    service.reply(TEAM, "manager-a", chat_id, message["id"])
    assert repo.get_chat(TEAM, "manager-a", chat_id)["messages"][-1] == message
    assert not llm.calls
