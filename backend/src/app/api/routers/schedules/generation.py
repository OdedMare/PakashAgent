"""Building a period: generated whole, as a resumable range job, or blank."""

from fastapi import APIRouter, Depends

from app.api.contracts import (
    BlankRequest, GenerateDayRequest, GenerateRequest, Schedule,
)
from app.api.routers.schedules.base import RouteGroup


def _required(request: GenerateRequest) -> list:
    return [item.model_dump() for item in request.required_assignments]


class GenerationRoutes(RouteGroup):
    def register(self, router: APIRouter) -> None:
        self._register_steps(router)
        self._register_control(router)

    def _register_steps(self, router: APIRouter) -> None:
        """Building a period: whole, as a range job, and one step of it."""
        service, boss = self.service, self.boss

        @router.post("/generate", response_model=Schedule)
        def generate(request: GenerateRequest, session: dict = Depends(boss)) -> dict:
            """Build a period. Stored as a draft — publishing is separate."""
            return service.generate(
                session["team_id"],
                starts_on=request.starts_on,
                ends_on=request.ends_on,
                instructions=request.instructions,
                required_assignments=_required(request),
            )

        @router.post("/generate/start", response_model=Schedule)
        def start_generation(
            request: GenerateRequest, session: dict = Depends(boss)
        ) -> dict:
            """Create a resumable range job. No model is called yet."""
            return service.start_generation(
                session["team_id"],
                starts_on=request.starts_on,
                ends_on=request.ends_on,
                instructions=request.instructions,
                required_assignments=_required(request),
            )

        @router.post("/generate/{schedule_id}/next", response_model=Schedule)
        def generate_next(schedule_id: str, session: dict = Depends(boss)) -> dict:
            """Generate and checkpoint one span; retry the failed one first."""
            return service.generate_next(session["team_id"], schedule_id)

    def _register_control(self, router: APIRouter) -> None:
        """Running, stopping, and narrowing a job; opening a blank period."""
        service, boss = self.service, self.boss

        @router.post("/generate/{schedule_id}/run", response_model=Schedule)
        def run_generation(schedule_id: str, session: dict = Depends(boss)) -> dict:
            """Launch generation and return immediately; progress is polled."""
            return service.queue_generation(session["team_id"], schedule_id)

        @router.post("/generate/{schedule_id}/cancel", response_model=Schedule)
        def cancel_generation(
            schedule_id: str, session: dict = Depends(boss)
        ) -> dict:
            """Stop waiting on a build. **Keeps every day already finished.**

            Cooperative rather than forceful: a model call already in flight
            cannot be interrupted, so this records the decision and the worker
            stops at the next day boundary. `POST /run` resumes the rest.
            """
            return service.cancel_generation(session["team_id"], schedule_id)

        @router.post("/generate/{schedule_id}/dismiss", response_model=Schedule)
        def dismiss_generation(
            schedule_id: str, session: dict = Depends(boss)
        ) -> dict:
            """Hide the banner of a stopped or failed build.

            The days already built stay, and `POST /run` still resumes it.
            """
            return service.dismiss_generation(session["team_id"], schedule_id)

        @router.post("/generate/{schedule_id}/day/start", response_model=Schedule)
        def start_day_generation(
            schedule_id: str,
            request: GenerateDayRequest,
            session: dict = Depends(boss),
        ) -> dict:
            """Prepare one existing draft date; no model call is held open."""
            return service.start_day_generation(
                session["team_id"], schedule_id,
                day=request.date, instructions=request.instructions,
            )

        @router.post("/blank", response_model=Schedule)
        def blank(request: BlankRequest, session: dict = Depends(boss)) -> dict:
            """Open an empty period the manager fills in themselves (D18).

            The authoring half of D6. No model is called on this path at all —
            the grid is arithmetic over the declared shift vocabulary.
            """
            return service.create_blank(
                session["team_id"],
                starts_on=request.starts_on,
                ends_on=request.ends_on,
            )
