"""A period leaving as a file (D17)."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.routers.schedules.base import RouteGroup

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TransferRoutes(RouteGroup):
    def register(self, router: APIRouter) -> None:
        self._register_export(router)

    def _register_export(self, router: APIRouter) -> None:
        """A period leaving as a file (D17)."""
        service, boss = self.service, self.boss

        @router.get("/export/{schedule_id}")
        def export(schedule_id: str, session: dict = Depends(boss)) -> Response:
            """One period as an `.xlsx` download.

            Boss-only: a file is a copy that leaves the app entirely. The
            filename is ASCII on purpose -- a Hebrew one travels badly through
            `Content-Disposition`.
            """
            content, name = service.workbook(session["team_id"], schedule_id)
            return Response(
                content=content,
                media_type=_XLSX,
                headers={"Content-Disposition": 'attachment; filename="%s"' % name},
            )
