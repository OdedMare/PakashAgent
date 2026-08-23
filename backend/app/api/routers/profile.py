"""Boss-only manual editing of employees and shift types."""

from fastapi import APIRouter, Depends

from app.api.contracts import ProfileUpdate


def build_router(service, guards) -> APIRouter:
    router = APIRouter(prefix="/api/profile", tags=["profile"])
    boss = guards.boss()

    @router.put("")
    def update(request: ProfileUpdate, session: dict = Depends(boss)) -> dict:
        return service.update(
            session["team_id"],
            employees=request.employees,
            shifts=request.shifts,
        )

    return router
