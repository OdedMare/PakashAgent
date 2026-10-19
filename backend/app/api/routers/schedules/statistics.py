"""The stats panel, filtered: a span of dates, optionally one person."""

from fastapi import APIRouter, Depends

from app.api.contracts import ShiftStats
from app.api.routers.schedules.base import RouteGroup


class StatisticsRoutes(RouteGroup):
    def register(self, router: APIRouter) -> None:
        service, boss = self.service, self.boss

        @router.get("/stats", response_model=ShiftStats)
        def stats(
            start: str, end: str, employee: str = "",
            session: dict = Depends(boss),
        ) -> dict:
            """The numbers for a day, a week, a month or any range.

            The same shape the overview carries for the current period, so
            the panel renders either without knowing which it was handed.
            `boss` and not `visitor`: load per person is the manager's view
            (D27), and the span reads drafts.
            """
            return service.stats(session["team_id"], start, end, employee)
