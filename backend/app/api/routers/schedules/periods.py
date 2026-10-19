"""Routes addressed by a period's id. **Registered last, on purpose.**

A path parameter at the root of the prefix matches any single segment, so
"/constraints" and "/history" would be read as schedule ids if these came
first. FastAPI resolves in declaration order, which makes the ordering
load-bearing rather than cosmetic.
"""

from fastapi import APIRouter, Depends

from app.api.contracts import ClearRequest, Schedule, ScheduleProgress
from app.api.routers.schedules.base import RouteGroup


class PeriodRoutes(RouteGroup):
    def register(self, router: APIRouter) -> None:
        service, boss = self.service, self.boss

        @router.post("/{schedule_id}/publish", response_model=Schedule)
        def publish(schedule_id: str, session: dict = Depends(boss)) -> dict:
            """Make a draft visible to the team."""
            return service.publish(schedule_id, session["team_id"])

        @router.post("/{schedule_id}/unpublish", response_model=Schedule)
        def unpublish(schedule_id: str, session: dict = Depends(boss)) -> dict:
            return service.unpublish(schedule_id, session["team_id"])

        @router.post("/{schedule_id}/clear", response_model=Schedule)
        def clear(
            schedule_id: str, request: ClearRequest, session: dict = Depends(boss),
        ) -> dict:
            """Empty a day's shifts, or the period's. The grid itself stays.

            Distinct from `DELETE /{schedule_id}`, which removes the period
            outright: the slots are the vocabulary's, not the build's.
            """
            return service.clear(
                session["team_id"], schedule_id,
                slot_date=request.slot_date, reason=request.reason,
            )

        @router.delete("/{schedule_id}")
        def delete(schedule_id: str, session: dict = Depends(boss)) -> dict:
            service.delete(schedule_id, session["team_id"])
            return {"status": "ok"}

        @router.get("/{schedule_id}/progress", response_model=ScheduleProgress)
        def progress(schedule_id: str, session: dict = Depends(boss)) -> dict:
            """How far a build has got. **The poll, and nothing more.**

            Separate from `GET /{schedule_id}` because the full period carries
            a fresh audit, and repeating that once a second to learn the agent
            is still on Tuesday is the cost this route removes.
            """
            return service.generation_progress(session["team_id"], schedule_id)

        @router.get("/{schedule_id}", response_model=Schedule)
        def get(schedule_id: str, session: dict = Depends(boss)) -> dict:
            return service.get(schedule_id, session["team_id"])
