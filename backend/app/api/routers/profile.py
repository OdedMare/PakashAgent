"""Boss-only manual editing of employees and shift types."""

from fastapi import APIRouter, Depends

from app.api.contracts import ProfileUpdate


def build_router(service, guards) -> APIRouter:
    router = APIRouter(prefix="/api/profile", tags=["profile"])
    boss = guards.boss()

    @router.get("/compiled")
    def compiled(session: dict = Depends(boss)) -> dict:
        """How each rule, policy and note was translated for the code
        scheduler (D32). Read-only; translating happens on save."""
        return {"sources": service.compiled(session["team_id"])}

    @router.put("")
    def update(request: ProfileUpdate, session: dict = Depends(boss)) -> dict:
        return service.update(
            session["team_id"], **request.model_dump(exclude_unset=True)
        )

    @router.delete("/shifts/{name}")
    def delete_shift(name: str, session: dict = Depends(boss)) -> dict:
        """Archive a shift type: the next build stops producing it, and
        schedules already stored keep their rows."""
        return service.delete_shift(session["team_id"], name)

    return router
