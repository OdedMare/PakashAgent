"""Boss-only control surface for the durable copilot."""

import time
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.contracts import CopilotPermissionUpdate


def build_router(service, repository, guards) -> APIRouter:
    router = APIRouter(prefix="/api/copilot", tags=["copilot"])
    boss = guards.boss()

    @router.get("/inbox")
    def inbox(
        status: Optional[str] = None, session: dict = Depends(boss)
    ) -> dict:
        return {
            "items": repository.copilot_items(session["team_id"], status),
            "permissions": repository.copilot_permissions(session["team_id"]),
            "health": repository.copilot_health(session["team_id"]),
        }

    @router.get("/audit")
    def audit(session: dict = Depends(boss)) -> dict:
        return {"events": repository.copilot_audit(session["team_id"])}

    @router.post("/run")
    def run_now(session: dict = Depends(boss)) -> dict:
        job = repository.enqueue_copilot_job(
            session["team_id"], "manual:%s" % time.time_ns()
        )
        return {"status": "queued", "job_id": job["id"]}

    @router.patch("/permissions/{action_type}")
    def permission(
        action_type: str, request: CopilotPermissionUpdate,
        session: dict = Depends(boss),
    ) -> dict:
        return repository.set_copilot_permission(
            session["team_id"], action_type, request.mode
        )

    @router.post("/items/{item_id}/approve")
    def approve(item_id: str, session: dict = Depends(boss)) -> dict:
        return service.approve(item_id, session["team_id"])

    @router.post("/items/{item_id}/dismiss")
    def dismiss(item_id: str, session: dict = Depends(boss)) -> dict:
        return service.dismiss(item_id, session["team_id"])

    @router.post("/items/{item_id}/rollback")
    def rollback(item_id: str, session: dict = Depends(boss)) -> dict:
        return service.rollback(item_id, session["team_id"])

    return router


__all__ = ["build_router"]
