"""Reading the management area: the overview, the period in play, a date."""

from fastapi import APIRouter, Depends

from app.api.contracts import ManagementOverview
from app.api.routers.schedules.base import RouteGroup


class ReadingRoutes(RouteGroup):
    def register(self, router: APIRouter) -> None:
        service, visitor = self.service, self.visitor

        @router.get("/overview", response_model=ManagementOverview)
        def overview(session: dict = Depends(visitor)) -> dict:
            """Everything the management area opens with.

            Served to members as well as the manager, and the role is passed
            down: a member gets published periods only, which is what makes
            their view a view of something finished rather than of the
            manager's working draft.
            """
            return service.overview(session["team_id"], session["role"])

        @router.get("/current")
        def current(session: dict = Depends(visitor)):
            """The period in play, or null when none has been built yet."""
            return service.current(session["team_id"], session["role"])

        @router.get("/at")
        def at(day: str, session: dict = Depends(visitor)):
            """The stored period containing a date, or null when none does.

            What the board opens on: which period covers today is a date
            comparison rather than something the client should infer.
            `visitor` and not `boss`: the role is passed down, so a member
            reaches only published periods exactly as `/current` gives them.
            """
            return service.period_at(session["team_id"], day, session["role"])
