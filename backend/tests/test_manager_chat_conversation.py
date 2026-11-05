"""How the conversation feels: drafts, follow-ups, editing and answering again."""

import datetime

import pytest

from app.bl.chat.draft import ReplyDraft, partial_reply
from app.bl.chat.schema import suggestions
from app.bl.chat.state import changes_since_reply
from app.common.errors import ConflictError
from tests.test_manager_chat import TEAM, converse, setup, sickness, turn


def said(reply):
    answer = turn()
    answer["reply"] = reply
    return answer


def test_the_reply_is_read_out_of_json_that_is_still_being_written():
    assert partial_reply('{"reply": "דנה עובדת\\nבשני') == "דנה עובדת\nבשני"
    assert partial_reply('{"reply": "סיימתי", "kind": "answer"}') == "סיימתי"
    assert partial_reply('{"kind": "ans') == ""
    # Half an escape is held back rather than shown as a wrong character.
    assert partial_reply('{"reply": "a\\u05') == "a"


def test_a_draft_is_written_a_few_times_a_second_not_per_token():
    written, now = [], [0.0]
    draft = ReplyDraft(written.append, clock=lambda: now[0])

    draft('{"reply": "ש')
    draft('{"reply": "של')
    now[0] = 1.0
    draft('{"reply": "שלום')

    assert written == ["ש", "שלום"]


def test_a_failed_draft_write_does_not_fail_the_turn():
    def broken(text):
        raise RuntimeError("database away")

    ReplyDraft(broken)('{"reply": "שלום')


def test_a_follow_up_that_would_approve_is_never_offered():
    offered = suggestions([
        "מי יכול להחליף את דנה ביום שלישי?", "אשר את התוכנית", "כן", "תבצע",
        "החל שינויים", "  תראה  לי את העומס  ", "x" * 81, "מי יכול להחליף את דנה ביום שלישי?",
    ])

    assert offered == ["מי יכול להחליף את דנה ביום שלישי?", "תראה לי את העומס"]


def test_the_models_follow_ups_reach_the_answer():
    answer = turn(suggestions=["מי עובד מחר?", "מאשר"])
    repo, llm, service, chat_id, schedule_id = setup([answer])

    message = converse(service, repo, chat_id, schedule_id, content="מה מצב השבוע?")

    assert message["payload"]["suggestions"] == ["מי עובד מחר?"]


def test_the_reply_so_far_is_saved_while_the_model_writes():
    class StreamingLlm:
        def __init__(self, answer):
            self.answer, self.calls = answer, []

        def complete_json(self, system, user, schema=None, flow="", time_context="", on_text=None):
            self.calls.append(user)
            on_text('{"reply": "בודק את השבוע')
            return self.answer

    repo, _, service, chat_id, schedule_id = setup([])
    service._reply._llm = StreamingLlm(turn())

    converse(service, repo, chat_id, schedule_id, content="מה מצב השבוע?")

    assert repo.drafts == ["בודק את השבוע"]


def test_an_edited_request_replaces_the_old_exchange():
    repo, llm, service, chat_id, schedule_id = setup([turn(), said("תשובה חדשה")])
    converse(service, repo, chat_id, schedule_id, content="מה המצב ביום שני?")
    asked = repo.get_chat(TEAM, "manager-a", chat_id)["messages"][0]

    message_id = service.start_turn(TEAM, "manager-a", chat_id, dict(
        content="מה המצב ביום שלישי?", request_id="request-2", schedule_id=schedule_id,
        replaces_message_id=asked["id"]))
    service.reply(TEAM, "manager-a", chat_id, message_id)

    messages = repo.get_chat(TEAM, "manager-a", chat_id)["messages"]
    assert [row["content"] for row in messages] == ["מה המצב ביום שלישי?", "תשובה חדשה"]


def test_an_edit_never_reads_as_approval_of_the_showing_plan():
    repo, llm, service, chat_id, schedule_id = setup([sickness(), said("בסדר")])
    converse(service, repo, chat_id, schedule_id)
    asked = repo.get_chat(TEAM, "manager-a", chat_id)["messages"][0]

    service.start_turn(TEAM, "manager-a", chat_id, dict(
        content="כן", request_id="request-2", schedule_id=schedule_id,
        replaces_message_id=asked["id"]))

    statuses = [row["status"] for row in repo.get_chat(TEAM, "manager-a", chat_id)["messages"]]
    assert "applied" not in statuses


def test_a_request_after_an_applied_plan_cannot_be_taken_back():
    repo, llm, service, chat_id, schedule_id = setup([sickness()])
    plan = converse(service, repo, chat_id, schedule_id)
    service.apply(TEAM, "manager-a", chat_id, plan["id"])
    asked = repo.get_chat(TEAM, "manager-a", chat_id)["messages"][0]

    with pytest.raises(ConflictError):
        service.start_turn(TEAM, "manager-a", chat_id, dict(
            content="משהו אחר", request_id="request-2", replaces_message_id=asked["id"]))


def test_answering_again_replaces_the_answer_and_shows_the_model_the_old_one():
    repo, llm, service, chat_id, schedule_id = setup([said("ראשונה"), said("שנייה")])
    converse(service, repo, chat_id, schedule_id, content="מה מצב השבוע?")

    message_id = service.regenerate(TEAM, "manager-a", chat_id, dict(
        request_id="again-1", schedule_id=schedule_id))
    service.reply(TEAM, "manager-a", chat_id, message_id)

    messages = repo.get_chat(TEAM, "manager-a", chat_id)["messages"]
    assert [row["content"] for row in messages] == ["מה מצב השבוע?", "שנייה"]
    assert '"previous_answer": "ראשונה"' in llm.calls[-1]["user"]


def test_an_applied_receipt_cannot_be_answered_again():
    repo, llm, service, chat_id, schedule_id = setup([sickness()])
    plan = converse(service, repo, chat_id, schedule_id)
    service.apply(TEAM, "manager-a", chat_id, plan["id"])

    with pytest.raises(ConflictError):
        service.regenerate(TEAM, "manager-a", chat_id, dict(request_id="again-1"))


def test_board_edits_since_the_last_answer_are_counted():
    earlier = datetime.datetime(2026, 10, 1, 9, 0)
    later = earlier + datetime.timedelta(minutes=5)
    messages = [
        {"id": "u", "role": "user", "created_at": earlier},
        {"id": "a", "role": "assistant", "status": "complete", "created_at": earlier},
        {"id": "w", "role": "assistant", "status": "working", "created_at": later},
    ]
    history = [{"created_at": later}, {"created_at": earlier}]

    assert changes_since_reply(history, messages, "w") == 1
    assert changes_since_reply(history, messages[:1], "w") == 0
