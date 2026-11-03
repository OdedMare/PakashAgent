"""Reading the management area: the overview, the period in play, a date,
a span of dates."""

from typing import List

from fastapi import APIRouter, Depends

from app.api.contracts import ManagementOverview, Schedule
from app.api.routers.schedules.base import RouteGroup


class ReadingRoutes(RouteGroup):
    def register(self, router: APIRouter) -> None:
        service, visitor, cache = self.service, self.visitor, self.cache

        @router.get("/overview", response_model=ManagementOverview)
        def overview(session: dict = Depends(visitor)) -> dict:
            """Everything the management area opens with.

            Served to members as well as the manager, and the role is passed
            down: a member gets published periods only, which is what makes
            their view a view of something finished rather than of the
            manager's working draft.
            """
            team, role = session["team_id"], session["role"]
            return cache.read(team, "overview", (role,),
                              lambda: service.overview(team, role))

        @router.get("/current")
        def current(session: dict = Depends(visitor)):
            """The period in play, or null when none has been built yet."""
            team, role = session["team_id"], session["role"]
            return cache.read(team, "current", (role,),
                              lambda: service.current(team, role))

        @router.get("/at")
        def at(day: str, session: dict = Depends(visitor)):
            """The stored period containing a date, or null when none does.

            What the board opens on: which period covers today is a date
            comparison rather than something the client should infer.
            `visitor` and not `boss`: the role is passed down, so a member
            reaches only published periods exactly as `/current` gives them.
            """
            team, role = session["team_id"], session["role"]
            return cache.read(team, "at", (day, role),
                              lambda: service.period_at(team, day, role))

        @router.get("/between", response_model=List[Schedule])
        def between(start: str, end: str, session: dict = Depends(visitor)):
            """Every stored period touching a span of dates, oldest first.

            What the board's two-week and month views read: one request for
            a span no single period covers. An empty list is a normal answer.
            `visitor` for the reason `/at` is — the role is passed down, and
            a member reaches published periods only.
            """
            team, role = session["team_id"], session["role"]
            return cache.read(team, "between", (start, end, role),
                              lambda: service.periods_between(team, start, end, role))
