"""Private chat routes; messages prepare plans, clicks approve stored plans."""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=1, max_length=80)
    schedule_id: Optional[str] = None
    visible_week: str = Field(default="", max_length=10)
    focus_date: str = Field(default="", max_length=10)
    approval_message_id: Optional[str] = Field(default=None, max_length=80)


class ChatApproval(BaseModel):
    accept_exceptions: bool = False


def build_router(service, repository, guards):
    router = APIRouter(prefix="/api/agent/chats", tags=["manager chat"])
    manager = guards.manager()

    @router.get("")
    def list_chats(session: dict = Depends(manager)):
        return repository.list_chats(session["team_id"], session["manager_id"])

    @router.post("")
    def create_chat(session: dict = Depends(manager)):
        return repository.create_chat(session["team_id"], session["manager_id"])

    @router.get("/{chat_id}")
    def get_chat(chat_id: str, from_message: str = Query(default="", max_length=80),
                 session: dict = Depends(manager)):
        return repository.get_chat(session["team_id"], session["manager_id"], chat_id,
                                   from_message=from_message)

    @router.delete("/{chat_id}")
    def delete_chat(chat_id: str, session: dict = Depends(manager)):
        repository.delete_chat(session["team_id"], session["manager_id"], chat_id)
        return {"status": "ok"}

    @router.post("/{chat_id}/messages")
    def message(chat_id: str, request: ChatTurn, background: BackgroundTasks,
                session: dict = Depends(manager)):
        message_id = service.start_turn(
            session["team_id"], session["manager_id"], chat_id, request.model_dump(),
        )
        if message_id:
            background.add_task(service.reply, session["team_id"], session["manager_id"],
                                chat_id, message_id)
        return repository.get_chat(session["team_id"], session["manager_id"], chat_id)

    @router.post("/{chat_id}/messages/{message_id}/apply")
    def apply(chat_id: str, message_id: str, request: ChatApproval,
              session: dict = Depends(manager)):
        return service.apply(session["team_id"], session["manager_id"], chat_id,
                             message_id, request.accept_exceptions)

    @router.post("/{chat_id}/messages/{message_id}/dismiss")
    def dismiss(chat_id: str, message_id: str, session: dict = Depends(manager)):
        repository.dismiss_chat_plan(session["team_id"], session["manager_id"],
                                     chat_id, message_id)
        return repository.get_chat(session["team_id"], session["manager_id"], chat_id)

    @router.post("/{chat_id}/stop")
    def stop(chat_id: str, session: dict = Depends(manager)):
        repository.stop_chat_turn(session["team_id"], session["manager_id"], chat_id)
        return repository.get_chat(session["team_id"], session["manager_id"], chat_id)

    return router
